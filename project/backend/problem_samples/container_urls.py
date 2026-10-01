from rest_framework.routers import DefaultRouter
from .views import ProblemContainerViewSet

router = DefaultRouter()
router.register('', ProblemContainerViewSet, basename='problem-container')
urlpatterns = router.urls
