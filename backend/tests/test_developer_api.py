import datetime
import unittest
from unittest.mock import MagicMock
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
from models import Binder, BinderCard, Card, CollectionItem, Set, User, UserSetting
from services.developer_api import (
    DEVELOPER_API_KEY_SETTING,
    authenticate_api_key,
    build_image_links,
    create_or_regenerate_api_key,
    generate_api_key,
    get_developer_binder_detail,
    get_developer_binders,
    get_developer_cards,
    get_developer_summary,
    get_user_api_key_info,
    revoke_api_key,
)
from api.developer import get_developer_user


class DeveloperApiTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine)
        self.db = Session()

        self.user = User(username="ash", hashed_password="pw", role="trainer", is_active=True, avatar_id=25)
        self.other_user = User(username="gary", hashed_password="pw", role="trainer", is_active=True, avatar_id=1)
        self.test_set = Set(id="base1", name="Base Set", lang="en")

        self.charizard = Card(
            id="base1-4_en",
            tcg_card_id="base1-4",
            name="Charizard",
            set_id="base1",
            number="4",
            rarity="Rare Holo",
            lang="en",
            price_trend=350.0,
            price_market=350.0,
            variants_holo=True,
            images_small="https://example.com/charizard_low.webp",
            images_large="https://example.com/charizard_high.webp",
        )
        self.pikachu = Card(
            id="base1-58_en",
            tcg_card_id="base1-58",
            name="Pikachu",
            set_id="base1",
            number="58",
            rarity="Common",
            lang="en",
            price_trend=15.0,
            price_market=15.0,
            variants_normal=True,
            images_small="https://example.com/pikachu_low.webp",
            images_large="https://example.com/pikachu_high.webp",
        )

        self.db.add_all([self.user, self.other_user, self.test_set, self.charizard, self.pikachu])
        self.db.commit()
        self.db.refresh(self.user)
        self.db.refresh(self.other_user)

    def tearDown(self):
        self.db.close()

    def test_api_key_generation_and_rotation(self):
        info_before = get_user_api_key_info(self.db, self.user.id)
        self.assertFalse(info_before["has_key"])
        self.assertIsNone(info_before["api_key"])

        created = create_or_regenerate_api_key(self.db, self.user.id)
        self.assertTrue(created["has_key"])
        self.assertTrue(created["api_key"].startswith("pk_live_"))
        self.assertIsNotNone(created["created_at"])

        info_after = get_user_api_key_info(self.db, self.user.id)
        self.assertTrue(info_after["has_key"])
        self.assertEqual(info_after["api_key"], created["api_key"])

        rotated = create_or_regenerate_api_key(self.db, self.user.id)
        self.assertNotEqual(rotated["api_key"], created["api_key"])
        self.assertTrue(rotated["api_key"].startswith("pk_live_"))

        revoke_api_key(self.db, self.user.id)
        info_revoked = get_user_api_key_info(self.db, self.user.id)
        self.assertFalse(info_revoked["has_key"])

    def test_authenticate_api_key(self):
        created = create_or_regenerate_api_key(self.db, self.user.id)
        valid_key = created["api_key"]

        user = authenticate_api_key(self.db, valid_key)
        self.assertIsNotNone(user)
        self.assertEqual(user.id, self.user.id)

        self.assertIsNone(authenticate_api_key(self.db, "invalid_key"))
        self.assertIsNone(authenticate_api_key(self.db, ""))
        self.assertIsNone(authenticate_api_key(self.db, None))

    def test_get_developer_user_dependency(self):
        created = create_or_regenerate_api_key(self.db, self.user.id)
        valid_key = created["api_key"]

        req = MagicMock()
        req.headers = {}
        # 1. Via X-API-Key
        user1 = get_developer_user(req, db=self.db, x_api_key=valid_key)
        self.assertEqual(user1.id, self.user.id)

        # 2. Via api_key query param
        user2 = get_developer_user(req, db=self.db, api_key_query=valid_key)
        self.assertEqual(user2.id, self.user.id)

        # 3. Via Bearer creds
        bearer = MagicMock()
        bearer.credentials = valid_key
        user3 = get_developer_user(req, db=self.db, bearer_creds=bearer)
        self.assertEqual(user3.id, self.user.id)

        # 4. Missing key raises 401
        with self.assertRaises(HTTPException) as ctx:
            get_developer_user(req, db=self.db)
        self.assertEqual(ctx.exception.status_code, 401)

        # 5. Invalid key raises 401
        with self.assertRaises(HTTPException) as ctx:
            get_developer_user(req, db=self.db, x_api_key="pk_live_nonexistent")
        self.assertEqual(ctx.exception.status_code, 401)

    def test_image_links_builder(self):
        req = MagicMock()
        req.base_url = "http://localhost:8000/"
        req.headers = {}

        links = build_image_links(req, self.charizard)
        self.assertEqual(links["small"], "https://example.com/charizard_low.webp")
        self.assertEqual(links["large"], "https://example.com/charizard_high.webp")
        self.assertEqual(links["local_small"], f"/api/images/card/{self.charizard.id}/low")
        self.assertEqual(links["local_large"], f"/api/images/card/{self.charizard.id}/high")
        self.assertEqual(links["url_large"], f"http://localhost:8000/api/images/card/{self.charizard.id}/high")

    def test_developer_summary_and_cards(self):
        item1 = CollectionItem(
            card_id=self.charizard.id,
            user_id=self.user.id,
            quantity=1,
            variant="Holo",
            condition="NM",
            purchase_price=200.0,
        )
        item2 = CollectionItem(
            card_id=self.pikachu.id,
            user_id=self.user.id,
            quantity=3,
            variant="Normal",
            condition="LP",
            purchase_price=5.0,
        )
        self.db.add_all([item1, item2])
        self.db.commit()

        summary = get_developer_summary(self.db, self.user, top_limit=5)
        self.assertEqual(summary["user"]["username"], "ash")
        self.assertEqual(summary["stats"]["total_cards"], 4)
        self.assertEqual(summary["stats"]["unique_cards"], 2)
        # charizard (350 * 1) + pikachu (15 * 3) = 395
        self.assertEqual(summary["stats"]["total_value"], 395.0)
        self.assertEqual(summary["stats"]["total_cost"], 215.0)
        self.assertGreater(summary["stats"]["pnl"], 0)
        self.assertEqual(len(summary["top_cards"]), 2)
        self.assertEqual(summary["top_cards"][0]["name"], "Charizard")
        self.assertEqual(summary["top_cards"][0]["total_value"], 350.0)
        self.assertEqual(summary["top_cards"][1]["name"], "Pikachu")
        self.assertEqual(summary["top_cards"][1]["total_value"], 45.0)

        # Query cards paginated
        cards_res = get_developer_cards(self.db, self.user, limit=10, offset=0, sort="value", order="desc")
        self.assertEqual(cards_res["total"], 2)
        self.assertEqual(len(cards_res["cards"]), 2)
        self.assertEqual(cards_res["cards"][0]["name"], "Charizard")

        # Search
        search_res = get_developer_cards(self.db, self.user, search="Pika")
        self.assertEqual(search_res["total"], 1)
        self.assertEqual(search_res["cards"][0]["name"], "Pikachu")

    def test_developer_binders(self):
        binder = Binder(
            name="Favorites",
            description="My best cards",
            color="#FF0000",
            user_id=self.user.id,
        )
        self.db.add(binder)
        self.db.commit()
        self.db.refresh(binder)

        bc = BinderCard(
            binder_id=binder.id,
            card_id=self.charizard.id,
            required_quantity=1,
        )
        self.db.add(bc)
        self.db.commit()

        binders_res = get_developer_binders(self.db, self.user)
        self.assertEqual(binders_res["total"], 1)
        self.assertEqual(binders_res["binders"][0]["name"], "Favorites")
        self.assertEqual(binders_res["binders"][0]["card_count"], 1)

        detail_res = get_developer_binder_detail(self.db, self.user, binder.id)
        self.assertEqual(detail_res["binder"]["name"], "Favorites")
        self.assertEqual(len(detail_res["cards"]), 1)
        self.assertEqual(detail_res["cards"][0]["name"], "Charizard")
        self.assertEqual(detail_res["cards"][0]["total_value"], 350.0)

    def test_settings_developer_key_endpoints(self):
        from api.settings import delete_developer_key, generate_developer_key, get_developer_key

        info1 = get_developer_key(db=self.db, current_user=self.user)
        self.assertFalse(info1["has_key"])

        gen = generate_developer_key(db=self.db, current_user=self.user)
        self.assertTrue(gen["has_key"])
        self.assertTrue(gen["api_key"].startswith("pk_live_"))

        info2 = get_developer_key(db=self.db, current_user=self.user)
        self.assertTrue(info2["has_key"])
        self.assertEqual(info2["api_key"], gen["api_key"])

        del_res = delete_developer_key(db=self.db, current_user=self.user)
        self.assertTrue(del_res["success"])

        info3 = get_developer_key(db=self.db, current_user=self.user)
        self.assertFalse(info3["has_key"])


if __name__ == "__main__":
    unittest.main()
