"""Django integration tests of type-scoped, independent container numbers."""
from django.test import TestCase
from accounts.models import Lab
from .labs import create_container
from .models import ProblemContainer


class SeparateContainerNumberingTests(TestCase):
    def setUp(self):
        self.edm = Lab.objects.create(name='Edmonton', code='EDM')
        self.other = Lab.objects.create(name='Calgary', code='CGY')

    def test_number_sequences_independent(self):
        pc1 = create_container(self.edm)
        dc1 = create_container(self.edm, is_dumping=True, source_container=pc1)
        pc2 = create_container(self.edm)
        dc2 = create_container(self.edm, is_dumping=True, source_container=pc2)
        self.assertEqual([x.container_id for x in (pc1, dc1, pc2, dc2)], [
            'EDM PC-00001', 'EDM DC-00001', 'EDM PC-00002', 'EDM DC-00002',
        ])
        self.edm.refresh_from_db()
        self.assertEqual(self.edm.next_container_number, 3)
        self.assertEqual(self.edm.next_dumping_container_number, 3)

    def test_resolver_cannot_confuse_pc_and_dc(self):
        pc = create_container(self.edm)
        dc = create_container(self.edm, is_dumping=True, source_container=pc)
        self.assertEqual(ProblemContainer.resolve_identifier('EDM PC-00001'), pc)
        self.assertEqual(ProblemContainer.resolve_identifier('EDM DC-00001'), dc)
        self.assertEqual(ProblemContainer.resolve_identifier('PC-1'), pc)
        self.assertEqual(ProblemContainer.resolve_identifier('DC-1'), dc)
        self.assertEqual(ProblemContainer.resolve_identifier('1'), pc)
        self.assertIsNone(ProblemContainer.resolve_identifier('DC-00002'))
        self.assertIsNone(ProblemContainer.resolve_identifier('CGY DC-00001'))

    def test_sequences_independent_across_labs(self):
        create_container(self.edm)
        create_container(self.edm, is_dumping=True)
        pc = create_container(self.other)
        dc = create_container(self.other, is_dumping=True, source_container=pc)
        self.assertEqual(pc.container_id, 'CGY PC-00001')
        self.assertEqual(dc.container_id, 'CGY DC-00001')
        self.assertEqual(ProblemContainer.resolve_identifier('CGY DC-00001'), dc)

    def test_legacy_labless_container_display_and_lookup(self):
        pc = ProblemContainer.objects.create()
        dc = ProblemContainer.objects.create(is_dumping=True)
        self.assertEqual(pc.container_id, f'PC-{pc.pk:06d}')
        self.assertEqual(dc.container_id, f'DC-{dc.pk:06d}')
        self.assertEqual(ProblemContainer.resolve_identifier(dc.container_id), dc)


class ReusedPhysicalNumberTests(TestCase):
    """Django-level regression tests (require DB and Django dependencies)."""

    def setUp(self):
        from django.contrib.auth.models import User
        from accounts.models import UserProfile
        from rest_framework.test import APIClient

        self.lab = Lab.objects.get(code='EDM')
        self.actor = User.objects.create_user(username='gap-reuse-user', email='gap-reuse@example.org')
        UserProfile.objects.create(user=self.actor, is_admin=True, role='lab_technician', lab=self.lab)
        self.client = APIClient()
        self.client.force_authenticate(self.actor)

    def test_new_pc_uses_old_dumping_gaps_before_next_high_number(self):
        ProblemContainer.objects.create(lab=self.lab, lab_number=1)
        ProblemContainer.objects.create(lab=self.lab, lab_number=3)
        ProblemContainer.objects.create(lab=self.lab, lab_number=6)
        ProblemContainer.objects.create(lab=self.lab, lab_number=1, is_dumping=True)
        Lab.objects.filter(pk=self.lab.pk).update(next_container_number=7, next_dumping_container_number=2)

        self.assertEqual(create_container(self.lab).container_id, 'EDM PC-00002')
        self.assertEqual(create_container(self.lab).container_id, 'EDM PC-00004')
        self.assertEqual(create_container(self.lab).container_id, 'EDM PC-00005')
        self.assertEqual(create_container(self.lab).container_id, 'EDM PC-00007')
        self.assertEqual(create_container(self.lab, is_dumping=True).container_id, 'EDM DC-00002')
        self.lab.refresh_from_db()
        self.assertEqual(self.lab.next_container_number, 8)
        self.assertEqual(self.lab.next_dumping_container_number, 3)

    def test_disposed_existing_pc_owns_its_number_until_reactivated(self):
        from django.utils import timezone
        ProblemContainer.objects.create(lab=self.lab, lab_number=1)
        disposed = ProblemContainer.objects.create(lab=self.lab, lab_number=2, disposed_at=timezone.now())
        ProblemContainer.objects.create(lab=self.lab, lab_number=4)
        self.assertEqual(create_container(self.lab).container_id, 'EDM PC-00003')
        self.assertEqual(ProblemContainer.resolve_identifier('EDM PC-00002'), disposed)

    def test_empty_legacy_pc_can_be_made_available_without_losing_audit(self):
        from django.utils import timezone
        disposed_time = timezone.now()
        container = ProblemContainer.objects.create(
            lab=self.lab, lab_number=3, disposed_at=disposed_time,
            disposed_by=self.actor, disposal_snapshot={'old': {'current_workflow': 'Disposed'}},
        )
        response = self.client.post(f'/api/problem-containers/{container.pk}/undo-disposal/', {},
                                    format='json', HTTP_X_CHANGE_REASON='Physical PC is empty')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['status'], 'empty')
        container.refresh_from_db()
        self.assertIsNone(container.disposed_at)
        self.assertIsNone(container.disposed_by_id)
        self.assertEqual(container.disposal_snapshot['old'], {'current_workflow': 'Disposed'})
        history = container.disposal_snapshot['_legacy_reactivation_events'][0]
        self.assertEqual(history['reason'], 'Physical PC is empty')
        self.assertEqual(history['disposed_by_id'], self.actor.pk)
        self.assertEqual(ProblemContainer.resolve_identifier('EDM PC-00003'), container)

    def test_dumping_container_cannot_be_made_available(self):
        from django.utils import timezone
        dump = ProblemContainer.objects.create(
            lab=self.lab, lab_number=1, is_dumping=True, disposed_at=timezone.now(),
        )
        response = self.client.post(f'/api/problem-containers/{dump.pk}/undo-disposal/', {}, format='json')
        self.assertEqual(response.status_code, 400)
        dump.refresh_from_db()
        self.assertIsNotNone(dump.disposed_at)
