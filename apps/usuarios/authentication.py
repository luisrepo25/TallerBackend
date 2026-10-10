from django.utils.translation import gettext_lazy as _
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import AuthenticationFailed, InvalidToken
from rest_framework_simplejwt.settings import api_settings

# Capa de presentacion (autenticacion). Sin reglas de negocio.


class JWTAuthenticationConSubtipos(JWTAuthentication):
    """Igual que JWTAuthentication, pero carga al usuario junto con su rol y sus subtipos
    (administrador / inspector tecnico / oficial de mando) en UNA sola consulta.

    Los permisos (`hasattr(usuario, "administrador")`) preguntan por los subtipos en cada
    peticion: sin esto cada pregunta era una consulta mas a la base. Con la base en la
    nube, cada consulta cuesta ~150-200 ms de ida y vuelta, asi que esto recorta casi la
    mitad del tiempo de respuesta.
    """

    def get_user(self, validated_token):
        try:
            user_id = validated_token[api_settings.USER_ID_CLAIM]
        except KeyError as exc:
            raise InvalidToken(_("Token contained no recognizable user identification")) from exc

        try:
            user = self.user_model.objects.select_related(
                "rol", "administrador", "inspectortecnico", "oficialmando"
            ).get(**{api_settings.USER_ID_FIELD: user_id})
        except self.user_model.DoesNotExist as exc:
            raise AuthenticationFailed(_("User not found"), code="user_not_found") from exc

        if not user.is_active:
            raise AuthenticationFailed(_("User is inactive"), code="user_inactive")
        return user
