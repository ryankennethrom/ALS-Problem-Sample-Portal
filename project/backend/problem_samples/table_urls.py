from rest_framework.routers import DefaultRouter
from .views import ProblemTableViewSet

router = DefaultRouter()
router.register('', ProblemTableViewSet, basename='problem-table')
urlpatterns = router.urls
