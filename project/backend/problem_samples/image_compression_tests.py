from io import BytesIO

from django.test import SimpleTestCase
from PIL import Image

from .image_processing import (
    MAX_STORED_IMAGE_EDGE,
    TARGET_STORED_IMAGE_BYTES,
    compress_problem_image,
)


class ProblemImageCompressionTests(SimpleTestCase):
    def _jpeg_bytes(self, size=(2400, 1800)):
        # Pillow's deterministic noise image gives the encoder enough detail to
        # exercise both quality and resize steps without external fixtures.
        noise = Image.effect_noise(size, 90).convert('RGB')
        source = BytesIO()
        noise.save(source, format='JPEG', quality=95)
        noise.close()
        return source.getvalue()

    def test_large_upload_is_webp_and_bounded(self):
        source = self._jpeg_bytes()
        compressed, filename = compress_problem_image(BytesIO(source), 'Phone Photo.JPG')

        self.assertTrue(filename.endswith('.webp'))
        self.assertLessEqual(len(compressed), TARGET_STORED_IMAGE_BYTES)

        with Image.open(BytesIO(compressed)) as image:
            self.assertEqual(image.format, 'WEBP')
            self.assertLessEqual(max(image.size), MAX_STORED_IMAGE_EDGE)

    def test_transparent_png_stays_viewable_as_webp(self):
        image = Image.new('RGBA', (900, 600), (20, 40, 60, 120))
        source = BytesIO()
        image.save(source, format='PNG')
        image.close()

        compressed, filename = compress_problem_image(BytesIO(source.getvalue()), 'sample label.png')
        self.assertEqual(filename, 'sample-label.webp')
        with Image.open(BytesIO(compressed)) as result:
            self.assertEqual(result.format, 'WEBP')
            self.assertIn(result.mode, {'RGB', 'RGBA'})
