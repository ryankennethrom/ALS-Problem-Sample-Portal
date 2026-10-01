from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .models import (
    ProblemContainer,
    ProblemSample,
    ProblemTable,
    PROBLEM_STATUS_DISPOSED,
    PROBLEM_STATUS_TO_BE_DISPOSED,
)


class DashboardReadyContainerTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(User.objects.create_user(username='dashboard.container.ready'))
        self.table = ProblemTable.objects.create(name='Container dashboard test')
        self.number = 0

    def sample(self, container, workflow):
        self.number += 1
        return ProblemSample.objects.create(
            table=self.table,
            problem_number=self.number,
            container=container,
            current_workflow=workflow,
            custom_values={'current-workflow': workflow},
        )

    def test_ready_container_count_matches_ready_to_dispose_rule(self):
        ready = ProblemContainer.objects.create()
        self.sample(ready, PROBLEM_STATUS_TO_BE_DISPOSED)
        self.sample(ready, PROBLEM_STATUS_DISPOSED)

        blocked = ProblemContainer.objects.create()
        self.sample(blocked, PROBLEM_STATUS_TO_BE_DISPOSED)
        self.sample(blocked, 'CS Follow-Up')

        ProblemContainer.objects.create()  # Empty containers never qualify.

        disposed = ProblemContainer.objects.create(disposed_at=timezone.now())
        self.sample(disposed, PROBLEM_STATUS_TO_BE_DISPOSED)

        response = self.client.get('/api/dashboard/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['counts']['containers_ready_to_dispose'], 1)
