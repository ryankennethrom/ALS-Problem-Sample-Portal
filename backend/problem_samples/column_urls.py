from rest_framework.routers import DefaultRouter
from .views import ProblemColumnViewSet

router = DefaultRouter()
router.register('', ProblemColumnViewSet, basename='problem-column')
urlpatterns = router.urls
