import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from services import image_disk_cache

try:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from database import Base
    from models import ImageCache

    DB_DEPS_AVAILABLE = True
except ModuleNotFoundError:
    DB_DEPS_AVAILABLE = False

try:
    from api import images as image_api

    API_DEPS_AVAILABLE = True
except ModuleNotFoundError:
    image_api = None
    API_DEPS_AVAILABLE = False


class ImageDiskCacheTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.old_root = image_disk_cache.CACHE_ROOT
        image_disk_cache.CACHE_ROOT = Path(self.temp_dir.name)

    def tearDown(self):
        image_disk_cache.CACHE_ROOT = self.old_root
        self.temp_dir.cleanup()

    def test_write_and_lookup_round_trip(self):
        key = "card:sv1-1_en:small:abc123"
        path = image_disk_cache.write(key, b"webp-bytes", "image/webp")
        found = image_disk_cache.lookup(key)
        self.assertIsNotNone(found)
        self.assertEqual(found[0], path)
        self.assertEqual(found[1], "image/webp")
        self.assertEqual(path.read_bytes(), b"webp-bytes")

    def test_card_ids_with_spaces_stay_inside_the_cache_root(self):
        key = "card:custom card#1:small:manual:stale"
        path = image_disk_cache.write(key, b"jpg", "image/jpeg")
        self.assertTrue(str(path).startswith(str(image_disk_cache.CACHE_ROOT)))
        self.assertEqual(image_disk_cache.lookup(key)[1], "image/jpeg")

    def test_size_token_is_not_confused_with_small_in_the_card_id(self):
        key = "card:promo-small:small:abc"
        image_disk_cache.write(key, b"ok", "image/webp")
        image_disk_cache.delete_card_images("promo-small")
        self.assertIsNone(image_disk_cache.lookup(key))

    def test_delete_card_images_removes_all_sizes(self):
        image_disk_cache.write("card:sv1-1_en:small:aaa", b"small", "image/webp")
        image_disk_cache.write("card:sv1-1_en:large:bbb", b"large", "image/webp")
        image_disk_cache.write("card:sv1-2_en:small:ccc", b"other", "image/webp")
        image_disk_cache.delete_card_images("sv1-1_en")
        self.assertIsNone(image_disk_cache.lookup("card:sv1-1_en:small:aaa"))
        self.assertIsNone(image_disk_cache.lookup("card:sv1-1_en:large:bbb"))
        self.assertIsNotNone(image_disk_cache.lookup("card:sv1-2_en:small:ccc"))

    def test_write_replaces_atomically_without_tmp_files(self):
        key = "set:sv1:logo"
        image_disk_cache.write(key, b"one", "image/webp")
        path = image_disk_cache.write(key, b"two", "image/png")
        self.assertEqual(path.read_bytes(), b"two")
        self.assertEqual(image_disk_cache.lookup(key)[1], "image/png")
        self.assertFalse(any(path.parent.glob("*.tmp")))

    def test_clear_cache_empties_the_folder_without_removing_the_root(self):
        image_disk_cache.write("card:sv1-1_en:small:abc", b"x", "image/webp")
        root = image_disk_cache.CACHE_ROOT
        self.assertTrue(any(root.iterdir()))
        image_disk_cache.clear_cache()
        self.assertTrue(root.is_dir())
        self.assertFalse(any(root.iterdir()))

    def test_product_and_set_keys_do_not_collide(self):
        product_key = "product:custom:" + ("a" * 64)
        image_disk_cache.write(product_key, b"box", "image/webp")
        image_disk_cache.write("set:sv1:symbol", b"sym", "image/png")
        self.assertEqual(image_disk_cache.lookup(product_key)[0].read_bytes(), b"box")
        self.assertEqual(image_disk_cache.lookup("set:sv1:symbol")[1], "image/png")


@unittest.skipUnless(DB_DEPS_AVAILABLE, "Backend database dependencies are not installed")
class ImageCachePurgeTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.old_root = image_disk_cache.CACHE_ROOT
        image_disk_cache.CACHE_ROOT = Path(self.temp_dir.name)
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.session = sessionmaker(bind=self.engine)()

    def tearDown(self):
        self.session.close()
        image_disk_cache.CACHE_ROOT = self.old_root
        self.temp_dir.cleanup()

    def test_purge_card_images_clears_db_and_disk(self):
        key = "card:sv1-1_en:small:abc"
        self.session.add(ImageCache(image_key=key, data=b"old", content_type="image/webp"))
        self.session.commit()
        image_disk_cache.write(key, b"old", "image/webp")

        image_disk_cache.purge_card_images(self.session, "sv1-1_en")
        self.session.commit()

        self.assertIsNone(self.session.query(ImageCache).filter(ImageCache.image_key == key).first())
        self.assertIsNone(image_disk_cache.lookup(key))


@unittest.skipUnless(API_DEPS_AVAILABLE and DB_DEPS_AVAILABLE, "Backend API dependencies are not installed")
class ImageProxyDiskCacheTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.old_root = image_disk_cache.CACHE_ROOT
        image_disk_cache.CACHE_ROOT = Path(self.temp_dir.name)
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.session = sessionmaker(bind=self.engine)()

    def tearDown(self):
        self.session.close()
        image_disk_cache.CACHE_ROOT = self.old_root
        self.temp_dir.cleanup()

    def test_get_or_fetch_uses_disk_without_network(self):
        key = "card:sv1-1_en:small:abc"
        image_disk_cache.write(key, b"cached-webp", "image/webp")
        with patch.object(image_api, "_client") as client:
            data, content_type = image_api._get_or_fetch(self.session, key, "https://assets.example/card.webp")
        self.assertEqual(data, b"cached-webp")
        self.assertEqual(content_type, "image/webp")
        client.get.assert_not_called()

    def test_get_or_fetch_copies_database_bytes_onto_disk(self):
        key = "card:sv1-1_en:small:abc"
        self.session.add(ImageCache(image_key=key, data=b"from-db", content_type="image/jpeg"))
        self.session.commit()
        with patch.object(image_api, "_client") as client:
            data, content_type = image_api._get_or_fetch(self.session, key, "https://assets.example/card.webp")
        self.assertEqual(data, b"from-db")
        self.assertEqual(content_type, "image/jpeg")
        client.get.assert_not_called()
        found = image_disk_cache.lookup(key)
        self.assertIsNotNone(found)
        self.assertEqual(found[0].read_bytes(), b"from-db")

    def test_get_or_fetch_writes_upstream_bytes_to_disk(self):
        key = "card:sv1-1_en:small:abc"
        response = Mock()
        response.content = b"upstream"
        response.headers = {"content-type": "image/webp"}
        response.raise_for_status = Mock()
        with patch.object(image_api, "_client") as client:
            client.get.return_value = response
            data, content_type = image_api._get_or_fetch(self.session, key, "https://assets.example/card.webp")
        self.assertEqual(data, b"upstream")
        self.assertEqual(content_type, "image/webp")
        found = image_disk_cache.lookup(key)
        self.assertEqual(found[0].read_bytes(), b"upstream")
        cached = self.session.query(ImageCache).filter(ImageCache.image_key == key).first()
        self.assertIsNotNone(cached)
        self.assertEqual(cached.data, b"upstream")


if __name__ == "__main__":
    unittest.main()
