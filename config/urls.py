from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

urlpatterns = [
    path("admin/", admin.site.urls),

    path("api/auth/token/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/auth/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),

    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),

    path("api/usuarios/", include("apps.usuarios.urls")),
    path("api/catastro/", include("apps.catastro.urls")),
    path("api/campanias/", include("apps.campanias.urls")),
    path("api/fiscalizacion/", include("apps.fiscalizacion.urls")),
    path("api/analitica/", include("apps.analitica.urls")),
    path("api/reportes/", include("apps.reportes.urls")),
]
