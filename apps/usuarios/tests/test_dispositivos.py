import io
import json
import urllib.error
import uuid
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, TestCase, override_settings
from rest_framework import status
from rest_framework.test import APIClient

from apps.common import fcm_cliente
from apps.usuarios.models import DispositivoNotificacion, Rol
from apps.usuarios.services import crear_usuario, notificar_usuarios

URL = "/api/usuarios/dispositivos/"
ENVIAR = "apps.usuarios.services.fcm_cliente.enviar"
HABILITADO = "apps.usuarios.services.fcm_cliente.habilitado"


class BaseDispositivosTestCase(TestCase):
    def setUp(self):
        self.suffix = uuid.uuid4().hex[:6]
        self.inspector = self._usuario("insp1")
        self.otro = self._usuario("insp2")
        self.client = APIClient()

    def _usuario(self, prefijo):
        return crear_usuario(
            nombre_completo=f"{prefijo} {self.suffix}",
            email=f"{prefijo}.{self.suffix}@uubr.org.bo",
            password="claveSegura123",
            rol=Rol.objects.get(nombre="Inspector Tecnico"),
            subtipo="inspector_tecnico",
        )

    def token(self, texto="a"):
        return f"tok-{self.suffix}-{texto}"


class RegistroDeDispositivosTests(BaseDispositivosTestCase):
    def test_registra_el_token_del_telefono(self):
        self.client.force_authenticate(self.inspector)

        r = self.client.post(URL, {"token": self.token()}, format="json")

        self.assertEqual(r.status_code, status.HTTP_204_NO_CONTENT)
        d = DispositivoNotificacion.objects.get(token=self.token())
        self.assertEqual(d.usuario_id, self.inspector.pk)
        self.assertEqual(d.plataforma, "android")

    def test_es_idempotente_la_app_lo_llama_en_cada_inicio(self):
        self.client.force_authenticate(self.inspector)
        for _ in range(3):
            self.client.post(URL, {"token": self.token()}, format="json")

        self.assertEqual(DispositivoNotificacion.objects.filter(token=self.token()).count(), 1)

    def test_si_otra_cuenta_inicia_sesion_en_el_telefono_el_token_pasa_a_ella(self):
        self.client.force_authenticate(self.inspector)
        self.client.post(URL, {"token": self.token()}, format="json")
        self.client.force_authenticate(self.otro)
        self.client.post(URL, {"token": self.token()}, format="json")

        d = DispositivoNotificacion.objects.get(token=self.token())
        self.assertEqual(d.usuario_id, self.otro.pk)

    def test_un_usuario_puede_tener_varios_dispositivos(self):
        self.client.force_authenticate(self.inspector)
        self.client.post(URL, {"token": self.token("a")}, format="json")
        self.client.post(URL, {"token": self.token("b")}, format="json")

        self.assertEqual(self.inspector.dispositivos.count(), 2)

    def test_token_vacio_o_plataforma_invalida_se_rechaza(self):
        self.client.force_authenticate(self.inspector)

        self.assertEqual(
            self.client.post(URL, {"token": ""}, format="json").status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertEqual(
            self.client.post(
                URL, {"token": self.token(), "plataforma": "windows"}, format="json"
            ).status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_cerrar_sesion_borra_el_token(self):
        self.client.force_authenticate(self.inspector)
        self.client.post(URL, {"token": self.token()}, format="json")

        r = self.client.delete(URL, {"token": self.token()}, format="json")

        self.assertEqual(r.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(DispositivoNotificacion.objects.filter(token=self.token()).exists())

    def test_no_se_puede_borrar_el_token_de_otro_usuario(self):
        self.client.force_authenticate(self.inspector)
        self.client.post(URL, {"token": self.token()}, format="json")
        self.client.force_authenticate(self.otro)

        r = self.client.delete(URL, {"token": self.token()}, format="json")

        self.assertEqual(r.status_code, status.HTTP_204_NO_CONTENT)
        self.assertTrue(DispositivoNotificacion.objects.filter(token=self.token()).exists())

    def test_sin_sesion_es_401(self):
        r = self.client.post(URL, {"token": self.token()}, format="json")
        self.assertEqual(r.status_code, status.HTTP_401_UNAUTHORIZED)


class NotificarUsuariosTests(BaseDispositivosTestCase):
    def setUp(self):
        super().setUp()
        DispositivoNotificacion.objects.create(usuario=self.inspector, token=self.token("a"))
        DispositivoNotificacion.objects.create(usuario=self.inspector, token=self.token("b"))
        DispositivoNotificacion.objects.create(usuario=self.otro, token=self.token("c"))

    def test_desactivadas_no_envia_ni_falla(self):
        with patch(HABILITADO, return_value=False), patch(ENVIAR) as enviar:
            self.assertEqual(notificar_usuarios([self.inspector.pk], titulo="t", cuerpo="c"), 0)
        enviar.assert_not_called()

    def test_envia_a_todos_los_dispositivos_de_esos_usuarios_y_a_nadie_mas(self):
        with patch(HABILITADO, return_value=True), patch(ENVIAR) as enviar:
            n = notificar_usuarios([self.inspector.pk], titulo="T", cuerpo="C", datos={"x": 1})

        self.assertEqual(n, 2)
        tokens = {llamada.args[0] for llamada in enviar.call_args_list}
        self.assertEqual(tokens, {self.token("a"), self.token("b")})
        self.assertEqual(enviar.call_args.kwargs["datos"], {"x": 1})

    def test_un_token_muerto_se_olvida(self):
        def enviar(token, **_):
            if token == self.token("a"):
                raise fcm_cliente.TokenInvalido("muerto")

        with patch(HABILITADO, return_value=True), patch(ENVIAR, side_effect=enviar):
            n = notificar_usuarios([self.inspector.pk], titulo="t", cuerpo="c")

        self.assertEqual(n, 1)
        self.assertFalse(DispositivoNotificacion.objects.filter(token=self.token("a")).exists())
        self.assertTrue(DispositivoNotificacion.objects.filter(token=self.token("b")).exists())

    def test_un_fallo_de_firebase_no_lanza_ni_borra_el_token(self):
        with (
            patch(HABILITADO, return_value=True),
            patch(ENVIAR, side_effect=fcm_cliente.FcmError("caido")),
        ):
            n = notificar_usuarios([self.inspector.pk], titulo="t", cuerpo="c")

        self.assertEqual(n, 0)
        self.assertEqual(self.inspector.dispositivos.count(), 2)

    def test_un_error_inesperado_tampoco_lanza(self):
        with patch(HABILITADO, return_value=True), patch(ENVIAR, side_effect=RuntimeError("x")):
            self.assertEqual(notificar_usuarios([self.inspector.pk], titulo="t", cuerpo="c"), 0)


def _http_error(codigo, cuerpo):
    return urllib.error.HTTPError(
        "https://fcm", codigo, "x", {}, io.BytesIO(json.dumps(cuerpo).encode())
    )


@override_settings(FIREBASE_CREDENTIALS_JSON="{}", FCM_TIMEOUT_SEGUNDOS=1)
class ClienteFcmTests(SimpleTestCase):
    def enviar(self, **kw):
        with patch.object(fcm_cliente, "_acceso", return_value=("acceso", "proyecto-x")):
            return fcm_cliente.enviar("tok", titulo="T", cuerpo="C", **kw)

    def test_el_mensaje_lleva_titulo_cuerpo_y_datos_como_texto(self):
        with patch("urllib.request.urlopen", return_value=MagicMock()) as abrir:
            self.enviar(datos={"campania_id": 7})

        peticion = abrir.call_args.args[0]
        self.assertIn("projects/proyecto-x/messages:send", peticion.full_url)
        self.assertEqual(peticion.get_header("Authorization"), "Bearer acceso")
        mensaje = json.loads(peticion.data)["message"]
        self.assertEqual(mensaje["token"], "tok")
        self.assertEqual(mensaje["notification"], {"title": "T", "body": "C"})
        self.assertEqual(mensaje["data"], {"campania_id": "7"})

    def test_token_desconocido_se_distingue_de_un_fallo_comun(self):
        cuerpo = {"error": {"details": [{"errorCode": "UNREGISTERED"}]}}
        with patch("urllib.request.urlopen", side_effect=_http_error(404, cuerpo)):
            with self.assertRaises(fcm_cliente.TokenInvalido):
                self.enviar()

    def test_otros_errores_http_son_fcm_error(self):
        with patch("urllib.request.urlopen", side_effect=_http_error(500, {})):
            with self.assertRaises(fcm_cliente.FcmError) as ctx:
                self.enviar()
        self.assertNotIsInstance(ctx.exception, fcm_cliente.TokenInvalido)

    def test_sin_red_es_fcm_error(self):
        with patch("urllib.request.urlopen", side_effect=TimeoutError("lento")):
            with self.assertRaises(fcm_cliente.FcmError):
                self.enviar()

    @override_settings(FIREBASE_CREDENTIALS_JSON="")
    def test_sin_credenciales_esta_deshabilitado(self):
        self.assertFalse(fcm_cliente.habilitado())
