from django.urls import path
from .views import ProblemAcknowledgementView, ProblemAcknowledgementImageView, ProblemAcknowledgementAttachmentView

urlpatterns = [
    path('<str:token>/', ProblemAcknowledgementView.as_view(), name='problem-acknowledgement'),
    path('<str:token>/images/<int:image_id>/', ProblemAcknowledgementImageView.as_view(), name='problem-acknowledgement-image'),
    path('<str:token>/attachments/<int:attachment_id>/', ProblemAcknowledgementAttachmentView.as_view(), name='problem-acknowledgement-attachment'),
]
