import uuid
from decimal import Decimal
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework import status

from apps.fiscalizacion.models import CatalogoMaterialCombustible, SolicitudMaterial
from apps.fiscalizacion.tests.test_fiscalizacion import BaseFiscalizacionTestCase


class SolicitudMaterialTests(BaseFiscalizacionTestCase):
    """El Inspector no crea materiales: los solicita y el Administrador los aprueba."""

    def setUp(self):
        super().setUp()
        self.url = reverse("fiscalizacion:solicitud-material-list")

    def solicitar(self, **cambios):
        datos = {"nombre": "Espuma de poliuretano", "descripcion": "Colchones", **cambios}
        self.client.force_authenticate(self.inspector)
        return self.client.post(self.url, datos, format="json")

    def test_inspector_solicita_un_material_nuevo(self):
        respuesta = self.solicitar(peso_kg_estimado="40.5")

        self.assertEqual(respuesta.status_code, status.HTTP_201_CREATED)
        self.assertEqual(respuesta.data["estado"], "pendiente")
        solicitud = SolicitudMaterial.objects.get(pk=respuesta.data["id"])
        self.assertEqual(solicitud.solicitante_id, self.inspector.pk)
        self.assertEqual(solicitud.peso_kg_estimado, Decimal("40.50"))

    def test_reenviar_el_mismo_uuid_no_duplica(self):
        identificador = str(uuid.uuid4())
        primera = self.solicitar(uuid_local=identificador)
        segunda = self.solicitar(uuid_local=identificador)

        self.assertEqual(segunda.status_code, status.HTTP_201_CREATED)
        self.assertEqual(primera.data["id"], segunda.data["id"])
        self.assertEqual(SolicitudMaterial.objects.filter(uuid_local=identificador).count(), 1)

    def test_no_se_puede_pedir_un_material_que_ya_existe(self):
        respuesta = self.solicitar(nombre=self.mat_madera.nombre.upper())

        self.assertEqual(respuesta.status_code, status.HTTP_409_CONFLICT)

    def test_no_se_puede_pedir_dos_veces_el_mismo_material_pendiente(self):
        self.solicitar()
        respuesta = self.solicitar()

        self.assertEqual(respuesta.status_code, status.HTTP_409_CONFLICT)

    def test_solo_el_inspector_puede_solicitar(self):
        self.client.force_authenticate(self.oficial)
        respuesta = self.client.post(self.url, {"nombre": "Algo"}, format="json")

        self.assertEqual(respuesta.status_code, status.HTTP_403_FORBIDDEN)

    def test_el_inspector_solo_ve_sus_solicitudes(self):
        self.solicitar()
        self.client.force_authenticate(self.inspector2)

        ajenas = self.client.get(self.url)
        self.client.force_authenticate(self.inspector)
        propias = self.client.get(self.url)

        self.assertEqual(len(ajenas.data), 0)
        self.assertEqual(len(propias.data), 1)

    def test_admin_aprueba_y_el_material_entra_al_catalogo(self):
        solicitud_id = self.solicitar().data["id"]
        self.client.force_authenticate(self.admin)

        respuesta = self.client.post(
            reverse("fiscalizacion:solicitud-material-aprobar", args=[solicitud_id]),
            {"poder_calorifico_mj_kg": "28.50", "coeficiente_peligrosidad": "1.40"},
            format="json",
        )

        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        self.assertEqual(respuesta.data["estado"], "aprobada")
        material = CatalogoMaterialCombustible.objects.get(nombre="Espuma de poliuretano")
        self.assertEqual(material.poder_calorifico_mj_kg, Decimal("28.50"))
        self.assertEqual(respuesta.data["material"], material.pk)

    def test_inspector_no_puede_aprobar(self):
        solicitud_id = self.solicitar().data["id"]

        respuesta = self.client.post(
            reverse("fiscalizacion:solicitud-material-aprobar", args=[solicitud_id]),
            {"poder_calorifico_mj_kg": "28.50", "coeficiente_peligrosidad": "1.40"},
            format="json",
        )

        self.assertEqual(respuesta.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(
            CatalogoMaterialCombustible.objects.filter(nombre__startswith="Espuma").exists()
        )

    def test_rechazar_exige_motivo_y_no_se_resuelve_dos_veces(self):
        solicitud_id = self.solicitar().data["id"]
        self.client.force_authenticate(self.admin)
        url = reverse("fiscalizacion:solicitud-material-rechazar", args=[solicitud_id])

        sin_motivo = self.client.post(url, {"motivo": "  "}, format="json")
        rechazada = self.client.post(url, {"motivo": "Ya cubierto por Plasticos"}, format="json")
        otra_vez = self.client.post(url, {"motivo": "Otra vez"}, format="json")

        self.assertEqual(sin_motivo.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(rechazada.data["estado"], "rechazada")
        self.assertEqual(otra_vez.status_code, status.HTTP_409_CONFLICT)


class SubirImagenEvidenciaTests(BaseFiscalizacionTestCase):
    def setUp(self):
        super().setUp()
        self.url = reverse("fiscalizacion:subir-evidencia")
        self.client.force_authenticate(self.inspector)

    def foto(self, nombre="foto.jpg", tipo="image/jpeg", contenido=b"\xff\xd8\xff fake"):
        return SimpleUploadedFile(nombre, contenido, content_type=tipo)

    @mock.patch("apps.fiscalizacion.services.cloudinary_storage.subir_imagen")
    def test_sube_la_foto_y_devuelve_la_url(self, subir):
        subir.return_value = "https://res.cloudinary.com/x/foto.jpg"

        respuesta = self.client.post(self.url, {"imagen": self.foto()}, format="multipart")

        self.assertEqual(respuesta.status_code, status.HTTP_201_CREATED)
        self.assertEqual(respuesta.data["url_imagen"], "https://res.cloudinary.com/x/foto.jpg")
        subir.assert_called_once()

    @mock.patch("apps.fiscalizacion.services.cloudinary_storage.subir_imagen")
    def test_rechaza_archivos_que_no_son_imagen(self, subir):
        respuesta = self.client.post(
            self.url,
            {"imagen": self.foto("virus.exe", "application/octet-stream")},
            format="multipart",
        )

        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        subir.assert_not_called()

    def test_sin_archivo_es_400(self):
        respuesta = self.client.post(self.url, {}, format="multipart")

        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)

    def test_solo_el_inspector_puede_subir(self):
        self.client.force_authenticate(self.oficial)

        respuesta = self.client.post(self.url, {"imagen": self.foto()}, format="multipart")

        self.assertEqual(respuesta.status_code, status.HTTP_403_FORBIDDEN)
