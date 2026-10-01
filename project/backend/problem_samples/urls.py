from rest_framework.routers import DefaultRouter
from .views import ProblemSampleViewSet

router = DefaultRouter()
router.register('', ProblemSampleViewSet, basename='problem-sample')
urlpatterns = router.urls
