"""Dependency-free tests for iPhone photo validation and normalization.

The production app installs pillow-heif to decode real HEIC bytes; these unit
checks isolate the format-independent logic even when PyPI is unavailable.
"""
from io import BytesIO
import importlib.util
from pathlib import Path
from unittest import TestCase, mock
import sys
import types

from PIL import Image


_SOURCE = Path(__file__).with_name('image_processing.py')


def _processing_module():
    fake_heif = types.ModuleType('pillow_heif')
    registration = []
    fake_heif.register_heif_opener = lambda: registration.append(True)
    with mock.patch.dict(sys.modules, {'pillow_heif': fake_heif}):
        spec = importlib.util.spec_from_file_location('_als_iphone_image_processing', _SOURCE)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module, registration


def _image_bytes(image_format):
    image = Image.new('RGB', (24, 16), (33, 79, 120))
    buffer = BytesIO()
    image.save(buffer, format=image_format)
    return buffer.getvalue()


class IphoneImageUploadPureTests(TestCase):
    def setUp(self):
        self.processing, self.registration = _processing_module()

    def test_heif_decoder_registered_at_import(self):
        self.assertEqual(self.registration, [True])

    def test_jpeg_bytes_with_heic_filename_are_accepted(self):
        source = BytesIO(_image_bytes('JPEG'))
        source.name = 'IMG_0250.heic'
        self.assertEqual(self.processing.validate_problem_image(source), '')
        self.assertEqual(source.tell(), 0)
        payload, filename = self.processing.compress_problem_image(source, source.name)
        self.assertEqual(filename, 'IMG_0250.webp')
        with Image.open(BytesIO(payload)) as output:
            self.assertEqual(output.format, 'WEBP')

    def test_jpeg_filename_never_overrides_real_png_format(self):
        source = BytesIO(_image_bytes('PNG'))
        source.name = 'IMG_0251.jpeg'
        self.assertEqual(self.processing.validate_problem_image(source), '')
        payload, filename = self.processing.compress_problem_image(source, source.name)
        self.assertEqual(filename, 'IMG_0251.webp')
        with Image.open(BytesIO(payload)) as output:
            self.assertEqual(output.format, 'WEBP')

    def test_heif_decoder_result_accepted_even_when_filename_is_jpeg(self):
        fake_picture = mock.MagicMock()
        fake_picture.__enter__.return_value.format = 'HEIF'
        fake_picture.__enter__.return_value.verify.return_value = None
        with mock.patch.object(self.processing.Image, 'open', return_value=fake_picture):
            self.assertEqual(self.processing.validate_problem_image(BytesIO(b'synthetic HEIF')), '')
        self.assertIn('HEIF', self.processing.ALLOWED_IMAGE_FORMATS)
        self.assertIn('HEIC', self.processing.ALLOWED_IMAGE_FORMATS)

    def test_unapproved_bmp_rejected_even_if_named_jpeg(self):
        source = BytesIO(_image_bytes('BMP'))
        source.name = 'IMG_0252.jpeg'
        self.assertIn('HEIC/HEIF', self.processing.validate_problem_image(source))
        self.assertEqual(source.tell(), 0)

    def test_corrupt_image_rejected_and_upload_rewound(self):
        source = BytesIO(b'not-an-image')
        source.name = 'IMG_0253.jpeg'
        self.assertEqual(self.processing.validate_problem_image(source), 'The selected file is not a valid image.')
        self.assertEqual(source.tell(), 0)
