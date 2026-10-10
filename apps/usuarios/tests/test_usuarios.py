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
