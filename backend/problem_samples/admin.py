from django.contrib import admin
from .models import ProblemSample, ProblemComment, ProblemImage, ProblemAttachment, ProblemTable, ProblemColumn, ProblemContainer

admin.site.register(ProblemTable)
admin.site.register(ProblemColumn)
admin.site.register(ProblemSample)
admin.site.register(ProblemComment)
admin.site.register(ProblemImage)
admin.site.register(ProblemAttachment)

admin.site.register(ProblemContainer)
