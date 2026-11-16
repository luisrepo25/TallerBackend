from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from apps.usuarios.models import BitacoraAuditoria, InspectorTecnico, Rol, Usuario
from apps.usuarios.services import crear_usuario, registrar_bitacora


class CrearUsuarioServiceTests(TestCase):
    def test_crea_usuario_y_subtipo_en_una_transaccion(self):
        rol = Rol.objects.get(nombre="Inspector Tecnico")

        usuario = crear_usuario(
            nombre_completo="Ana Perez",
            email="ana.perez@uubr.org.bo",
            password="claveSegura123",
            rol=rol,
            subtipo="inspector_tecnico",
            datos_subtipo={"curso_capacitacion_completo": True},
        )

        self.assertTrue(Usuario.objects.filter(email="ana.perez@uubr.org.bo").exists())
        subtipo = InspectorTecnico.objects.get(usuario=usuario)
        self.assertTrue(subtipo.curso_capacitacion_completo)
        # La password se guarda hasheada, nunca en texto plano.
        self.assertNotEqual(usuario.password, "claveSegura123")
        self.assertTrue(usuario.check_password("claveSegura123"))


class LoginJWTTests(TestCase):
    def setUp(self):
        self.rol = Rol.objects.get(nombre="Administrador")
        self.usuario = crear_usuario(
            nombre_completo="Carlos Mamani",
            email="carlos.mamani@uubr.org.bo",
            password="claveSegura123",
            rol=self.rol,
            subtipo="administrador",
        )
        self.client = APIClient()

    def test_login_valido_devuelve_tokens(self):
        response = self.client.post(
            reverse("token_obtain_pair"),
            {"email": "carlos.mamani@uubr.org.bo", "password": "claveSegura123"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)

    def test_login_invalido_rechaza_password_incorrecta(self):
        response = self.client.post(
            reverse("token_obtain_pair"),
            {"email": "carlos.mamani@uubr.org.bo", "password": "incorrecta"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class BitacoraAuditoriaTests(TestCase):
    def test_registrar_bitacora_guarda_snapshot_del_rol_actual(self):
        rol = Rol.objects.get(nombre="Oficial de Mando")
        usuario = crear_usuario(
            nombre_completo="Luisa Rojas",
            email="luisa.rojas@uubr.org.bo",
            password="claveSegura123",
            rol=rol,
            subtipo="oficial_mando",
        )

        registrar_bitacora(usuario=usuario, accion="Cerrar acta", entidad_afectada="ActaInspeccion")

        entrada = BitacoraAuditoria.objects.get(usuario=usuario)
        self.assertEqual(entrada.accion, "Cerrar acta")
        self.assertEqual(entrada.rol_id, rol.id)


class RolPermisoUsuarioViewSetPermissionTests(TestCase):
    """Verifica que los endpoints CRUD de roles/permisos/usuarios solo sean
    accesibles para el subtipo Administrador (RF-2), no para cualquier rol."""

    def setUp(self):
        rol_admin = Rol.objects.get(nombre="Administrador")
        rol_inspector = Rol.objects.get(nombre="Inspector Tecnico")

        self.administrador = crear_usuario(
            nombre_completo="Admin Uno",
            email="admin.uno@uubr.org.bo",
            password="claveSegura123",
            rol=rol_admin,
            subtipo="administrador",
        )
        self.inspector = crear_usuario(
            nombre_completo="Inspector Uno",
            email="inspector.uno@uubr.org.bo",
            password="claveSegura123",
            rol=rol_inspector,
            subtipo="inspector_tecnico",
        )
        self.client = APIClient()

    def test_administrador_puede_listar_roles(self):
        self.client.force_authenticate(user=self.administrador)
        response = self.client.get(reverse("usuarios:rol-list"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_inspector_no_puede_listar_roles(self):
        self.client.force_authenticate(user=self.inspector)
        response = self.client.get(reverse("usuarios:rol-list"))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_usuario_no_autenticado_no_puede_listar_usuarios(self):
        response = self.client.get(reverse("usuarios:usuario-list"))
        self.assertIn(
            response.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)
        )

    def test_administrador_puede_crear_usuario_via_endpoint(self):
        self.client.force_authenticate(user=self.administrador)
        rol_inspector = Rol.objects.get(nombre="Inspector Tecnico")

        response = self.client.post(
            reverse("usuarios:usuario-list"),
            {
                "nombre_completo": "Nuevo Inspector",
                "email": "nuevo.inspector@uubr.org.bo",
                "password": "claveSegura123",
                "rol": rol_inspector.id,
                "subtipo": "inspector_tecnico",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Usuario.objects.filter(email="nuevo.inspector@uubr.org.bo").exists())

    def test_inspector_no_puede_crear_usuario_via_endpoint(self):
        self.client.force_authenticate(user=self.inspector)
        rol_inspector = Rol.objects.get(nombre="Inspector Tecnico")

        response = self.client.post(
            reverse("usuarios:usuario-list"),
            {
                "nombre_completo": "Otro Inspector",
                "email": "otro.inspector@uubr.org.bo",
                "password": "claveSegura123",
                "rol": rol_inspector.id,
                "subtipo": "inspector_tecnico",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class PerfilTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_perfil_devuelve_usuario_con_sus_subtipos(self):
        usuario = crear_usuario(
            nombre_completo="Rosa Vaca",
            email="rosa.vaca@uubr.org.bo",
            password="claveSegura123",
            rol=Rol.objects.get(nombre="Oficial de Mando"),
            subtipo="oficial_mando",
        )
        # Los subtipos se solapan: tambien es Inspector Tecnico.
        InspectorTecnico.objects.create(usuario=usuario)
        self.client.force_authenticate(usuario)

        response = self.client.get(reverse("usuarios:perfil"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["email"], "rosa.vaca@uubr.org.bo")
        self.assertCountEqual(response.data["subtipos"], ["oficial_mando", "inspector_tecnico"])
        self.assertNotIn("password", response.data)

    def test_perfil_requiere_autenticacion(self):
        response = self.client.get(reverse("usuarios:perfil"))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class ConsultasPorPeticionTests(TestCase):
    """La base esta en la nube: cada consulta cuesta ~150-200 ms. Se vigila que el
    perfil y los permisos no vuelvan a disparar consultas de mas."""

    def test_perfil_se_resuelve_con_una_sola_consulta(self):
        usuario = crear_usuario(
            nombre_completo="Eva Rios",
            email="eva.rios@uubr.org.bo",
            password="claveSegura123",
            rol=Rol.objects.get(nombre="Administrador"),
            subtipo="administrador",
        )
        token = AccessToken.for_user(usuario)
        cliente = APIClient()
        cliente.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        # Autenticacion (usuario + rol + subtipos): 1 consulta; permisos y serializer: 0
        with self.assertNumQueries(1):
            respuesta = cliente.get(reverse("usuarios:perfil"))

        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        self.assertEqual(respuesta.data["subtipos"], ["administrador"])

    def test_el_permiso_de_subtipo_no_agrega_consultas(self):
        usuario = crear_usuario(
            nombre_completo="Ivo Paz",
            email="ivo.paz@uubr.org.bo",
            password="claveSegura123",
            rol=Rol.objects.get(nombre="Inspector Tecnico"),
            subtipo="inspector_tecnico",
        )
        token = AccessToken.for_user(usuario)
        cliente = APIClient()
        cliente.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        # Un Inspector pidiendo un recurso de Administrador: se rechaza (403) y solo
        # cuesta la consulta de autenticacion
        with self.assertNumQueries(1):
            respuesta = cliente.get(reverse("usuarios:rol-list"))

        self.assertEqual(respuesta.status_code, status.HTTP_403_FORBIDDEN)


class ActualizarUsuarioTests(TestCase):
    def setUp(self):
        self.admin = crear_usuario(
            nombre_completo="Admin Principal",
            email="admin.princ@uubr.org.bo",
            password="claveSegura123",
            rol=Rol.objects.get(nombre="Administrador"),
            subtipo="administrador",
        )
        self.inspector = crear_usuario(
            nombre_completo="Inspector Original",
            email="inspector.orig@uubr.org.bo",
            password="claveSegura123",
            rol=Rol.objects.get(nombre="Inspector Tecnico"),
            subtipo="inspector_tecnico",
            telefono="71112233",
        )
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def test_admin_puede_actualizar_telefono_y_nombre(self):
        url = reverse("usuarios:usuario-detail", args=[self.inspector.id])
        resp = self.client.patch(
            url,
            {"nombre_completo": "Inspector Modificado", "telefono": "75695707"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.inspector.refresh_from_db()
        self.assertEqual(self.inspector.nombre_completo, "Inspector Modificado")
        self.assertEqual(self.inspector.telefono, "75695707")


class ConsultaBitacoraTests(TestCase):
    """CU03: la bitacora se consulta solo como Administrador, con filtros y tope.

    Los tests corren sobre la BD compartida (ver settings.py), que ya tiene registros
    reales: por eso cada consulta se acota a los usuarios creados aqui.
    """

    def setUp(self):
        self.administrador = crear_usuario(
            nombre_completo="Admin Bitacora",
            email="admin.bitacora@uubr.org.bo",
            password="claveSegura123",
            rol=Rol.objects.get(nombre="Administrador"),
            subtipo="administrador",
        )
        self.inspector = crear_usuario(
            nombre_completo="Inspector Bitacora",
            email="inspector.bitacora@uubr.org.bo",
            password="claveSegura123",
            rol=Rol.objects.get(nombre="Inspector Tecnico"),
            subtipo="inspector_tecnico",
        )
        registrar_bitacora(
            usuario=self.administrador, accion="Crear campania", entidad_afectada="Campania"
        )
        registrar_bitacora(
            usuario=self.inspector, accion="Zzz accion de prueba", entidad_afectada="ActaInspeccion"
        )
        registrar_bitacora(
            usuario=self.inspector, accion="Zzz accion de prueba", entidad_afectada="ActaInspeccion"
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.administrador)
        self.url = reverse("usuarios:bitacora")

    def test_lista_con_el_mas_reciente_primero_y_snapshot_del_rol(self):
        datos = self.client.get(self.url, {"usuario_id": self.inspector.id}).json()

        self.assertEqual(len(datos), 2)
        self.assertGreater(datos[0]["id"], datos[1]["id"])
        self.assertEqual(datos[0]["rol"], "Inspector Tecnico")
        self.assertEqual(datos[0]["usuario_email"], "inspector.bitacora@uubr.org.bo")

    def test_filtra_por_usuario_y_por_accion(self):
        por_usuario = self.client.get(self.url, {"usuario_id": self.administrador.id}).json()
        por_accion = self.client.get(self.url, {"accion": "Zzz accion de prueba"}).json()

        self.assertEqual([r["accion"] for r in por_usuario], ["Crear campania"])
        self.assertEqual({r["usuario_id"] for r in por_accion}, {self.inspector.id})

    def test_filtra_por_rango_de_fechas(self):
        filtro = {"usuario_id": self.inspector.id}
        hoy = (
            BitacoraAuditoria.objects.filter(usuario=self.inspector)
            .first()
            .fecha.date()
            .isoformat()
        )

        self.assertEqual(
            len(self.client.get(self.url, {**filtro, "desde": hoy, "hasta": hoy}).json()), 2
        )
        self.assertEqual(self.client.get(self.url, {**filtro, "desde": "2999-01-01"}).json(), [])

    def test_rango_invertido_devuelve_400_con_el_campo(self):
        response = self.client.get(self.url, {"desde": "2026-10-10", "hasta": "2026-10-01"})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("hasta", response.json())

    def test_el_limite_acota_los_resultados(self):
        self.assertEqual(len(self.client.get(self.url, {"limite": 1}).json()), 1)

    def test_acciones_distintas_para_el_filtro(self):
        acciones = self.client.get(reverse("usuarios:bitacora-acciones")).json()

        self.assertEqual(acciones.count("Zzz accion de prueba"), 1)
        self.assertIn("Crear campania", acciones)

    def test_solo_el_administrador_puede_consultarla(self):
        self.client.force_authenticate(user=self.inspector)
        self.assertEqual(self.client.get(self.url).status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(
            self.client.get(reverse("usuarios:bitacora-acciones")).status_code,
            status.HTTP_403_FORBIDDEN,
        )

        self.client.force_authenticate(user=None)
        self.assertIn(
            self.client.get(self.url).status_code,
            (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
        )
