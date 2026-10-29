import http.cookiejar
import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener

import server


class TradeHubAPITests(unittest.TestCase):
    OWNER_USERNAME = "owner-prive-2026"
    OWNER_PASSWORD = "Owner-Secure-2026!"

    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        server.DB_PATH = Path(cls.temp_dir.name) / "test.sqlite3"
        server.MEDIA_DIR = Path(cls.temp_dir.name) / "uploads"
        server.BOOTSTRAP_SECRET = "test-setup-key-" + "x" * 40
        server.initialize_db()
        cls.httpd = server.TradeHubServer(("127.0.0.1", 0), server.TradeHubHandler)
        cls.base_url = "http://127.0.0.1:" + str(cls.httpd.server_address[1])
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.thread.join(timeout=2)
        cls.temp_dir.cleanup()

    def setUp(self):
        with server.connect_db() as db:
            db.execute("DELETE FROM users")
            db.execute("DELETE FROM owner_messages")
            for key, value in server.DEFAULT_SETTINGS.items():
                db.execute("UPDATE settings SET value=? WHERE key=?", (value, key))
        if server.MEDIA_DIR.exists():
            for media_file in server.MEDIA_DIR.iterdir():
                if media_file.is_file():
                    media_file.unlink()
        self.client = self.new_client()
        self.owner = self.new_client()
        self.seller = self.new_client()

    @staticmethod
    def new_client():
        return build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def request(self, client, path, method="GET", data=None, expected=200):
        body = None if data is None else json.dumps(data).encode("utf-8")
        request = Request(
            self.base_url + path,
            data=body,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        try:
            response = client.open(request, timeout=5)
            status = response.status
            result = json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            status = error.code
            result = json.loads(error.read().decode("utf-8"))
        self.assertEqual(status, expected, result)
        return result

    def upload_file(self, client, path, filename, content, expected=201):
        boundary = "----TradeHubTestBoundary"
        body = (
            ("--" + boundary + "\r\n").encode("ascii")
            + ('Content-Disposition: form-data; name="file"; filename="' + filename + '"\r\n').encode("ascii")
            + b"Content-Type: application/octet-stream\r\n\r\n"
            + content
            + ("\r\n--" + boundary + "--\r\n").encode("ascii")
        )
        request = Request(
            self.base_url + path,
            data=body,
            method="POST",
            headers={"Content-Type": "multipart/form-data; boundary=" + boundary},
        )
        try:
            response = client.open(request, timeout=5)
            status = response.status
            result = json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            status = error.code
            result = json.loads(error.read().decode("utf-8"))
        self.assertEqual(status, expected, result)
        return result

    def test_owner_bootstrap_requires_private_username_and_strong_password(self):
        self.request(
            self.owner,
            "/api/setup",
            "POST",
            {"setup_key": server.BOOTSTRAP_SECRET, "password": self.OWNER_PASSWORD},
            400,
        )
        self.request(
            self.owner,
            "/api/setup",
            "POST",
            {
                "setup_key": server.BOOTSTRAP_SECRET,
                "username": self.OWNER_USERNAME,
                "password": "weak-password",
            },
            400,
        )
        result = self.request(
            self.owner,
            "/api/setup",
            "POST",
            {
                "setup_key": server.BOOTSTRAP_SECRET,
                "username": self.OWNER_USERNAME,
                "password": self.OWNER_PASSWORD,
            },
            201,
        )
        self.assertNotIn("username", result)
        self.assertEqual(
            self.request(self.client, "/api/status")["owner_configured"],
            True,
        )

    def test_owner_bootstrap_and_server_side_permissions(self):
        self.request(
            self.owner,
            "/api/setup",
            "POST",
            {
                "setup_key": server.BOOTSTRAP_SECRET,
                "username": self.OWNER_USERNAME,
                "password": self.OWNER_PASSWORD,
            },
            201,
        )
        self.request(
            self.owner,
            "/api/login",
            "POST",
            {"username": self.OWNER_USERNAME, "password": self.OWNER_PASSWORD},
        )
        self.request(
            self.client,
            "/api/register",
            "POST",
            {"username": "client-one", "password": "customer-password-2026"},
            200,
        )
        self.request(self.client, "/api/admin/overview", expected=403)
        self.request(self.client, "/api/admin/settings", expected=403)
        self.request(
            self.client,
            "/api/admin/sellers",
            "POST",
            {"username": "forbidden", "store_name": "Intrus", "password": "seller-password-2026"},
            403,
        )
        self.request(
            self.client,
            "/api/register",
            "POST",
            {"username": self.OWNER_USERNAME, "password": "customer-password-2026"},
            409,
        )

    def test_owner_can_upload_logo_and_16_9_ad_video(self):
        self.upload_file(
            self.client,
            "/api/admin/media/logo",
            "logo.png",
            b"\x89PNG\r\n\x1a\nlogo-data",
            401,
        )
        self.request(
            self.owner,
            "/api/setup",
            "POST",
            {
                "setup_key": server.BOOTSTRAP_SECRET,
                "username": self.OWNER_USERNAME,
                "password": self.OWNER_PASSWORD,
            },
            201,
        )
        self.request(
            self.owner,
            "/api/login",
            "POST",
            {"username": self.OWNER_USERNAME, "password": self.OWNER_PASSWORD},
        )
        self.request(
            self.client,
            "/api/register",
            "POST",
            {"username": "client-upload", "password": "customer-password-2026"},
            200,
        )
        self.upload_file(
            self.client,
            "/api/admin/media/video",
            "pub.mp4",
            b"\x00\x00\x00\x18ftypisomadvertisement",
            403,
        )
        self.upload_file(
            self.client,
            "/api/admin/media/hero",
            "hero.png",
            b"\x89PNG\r\n\x1a\nhero-data",
            403,
        )
        self.upload_file(
            self.client,
            "/api/admin/media/hero-video",
            "hero-motion.mp4",
            b"\x00\x00\x00\x18ftypisommotion",
            403,
        )
        logo = self.upload_file(
            self.owner,
            "/api/admin/media/logo",
            "logo.png",
            b"\x89PNG\r\n\x1a\nlogo-data",
        )
        hero = self.upload_file(
            self.owner,
            "/api/admin/media/hero",
            "hero.png",
            b"\x89PNG\r\n\x1a\nhero-data",
        )
        hero_video = self.upload_file(
            self.owner,
            "/api/admin/media/hero-video",
            "hero-motion.mp4",
            b"\x00\x00\x00\x18ftypisommotion",
        )
        video = self.upload_file(
            self.owner,
            "/api/admin/media/video",
            "pub.mp4",
            b"\x00\x00\x00\x18ftypisomadvertisement",
        )
        settings = self.request(self.client, "/api/status")["settings"]
        self.assertEqual(settings["logo_url"], logo["url"])
        self.assertEqual(settings["hero_image_url"], hero["url"])
        self.assertEqual(settings["hero_video_url"], hero_video["url"])
        self.assertEqual(settings["ad_video_url"], video["url"])

        video_request = Request(self.base_url + video["url"], headers={"Range": "bytes=0-7"})
        response = self.client.open(video_request, timeout=5)
        self.assertEqual(response.status, 206)
        self.assertEqual(response.headers["Content-Type"], "video/mp4")
        self.assertEqual(response.headers["Content-Range"], "bytes 0-7/25")
        self.assertEqual(response.read(), b"\x00\x00\x00\x18ftyp")

    def test_seller_approval_product_lifecycle_and_live_settings(self):
        self.request(
            self.owner,
            "/api/setup",
            "POST",
            {
                "setup_key": server.BOOTSTRAP_SECRET,
                "username": self.OWNER_USERNAME,
                "password": self.OWNER_PASSWORD,
            },
            201,
        )
        self.request(
            self.owner,
            "/api/login",
            "POST",
            {"username": self.OWNER_USERNAME, "password": self.OWNER_PASSWORD},
        )
        seller = self.request(
            self.owner,
            "/api/admin/sellers",
            "POST",
            {
                "username": "marchand-1",
                "store_name": "Boutique Soleil",
                "whatsapp": "50937123456",
                "password": "seller-password-2026",
            },
            201,
        )
        self.upload_file(
            self.client,
            "/api/admin/sellers/" + str(seller["id"]) + "/profile-photo",
            "seller.jpg",
            b"\xff\xd8\xffseller-photo",
            401,
        )
        seller_photo = self.upload_file(
            self.owner,
            "/api/admin/sellers/" + str(seller["id"]) + "/profile-photo",
            "seller.jpg",
            b"\xff\xd8\xffseller-photo",
        )
        self.assertEqual(
            self.request(self.owner, "/api/admin/overview")["sellers"][0]["profile_image_url"],
            seller_photo["url"],
        )
        self.request(
            self.seller,
            "/api/login",
            "POST",
            {"username": "marchand-1", "password": "seller-password-2026"},
        )
        product = {
            "name": "Café des mornes",
            "description": "Café local fraîchement torréfié.",
            "price": 750,
            "stock": 12,
            "image_url": "https://example.com/cafe.jpg",
        }
        self.request(self.seller, "/api/products", "POST", product, 403)
        self.request(
            self.owner,
            "/api/admin/sellers/" + str(seller["id"]),
            "PATCH",
            {"action": "approve"},
        )
        created = self.request(self.seller, "/api/products", "POST", product, 201)
        product_id = created["id"]
        seller_products = self.request(self.seller, "/api/seller/products")
        self.assertEqual(seller_products["products"][0]["name"], product["name"])
        self.assertEqual(seller_products["seller"]["profile_image_url"], seller_photo["url"])
        updated = dict(product, name="Café du marché", price=800)
        self.request(self.seller, "/api/products/" + str(product_id), "PATCH", updated)
        visible = self.request(self.client, "/api/products")["products"]
        self.assertEqual(visible[0]["name"], "Café du marché")
        self.assertEqual(visible[0]["profile_image_url"], seller_photo["url"])
        self.request(
            self.owner,
            "/api/admin/settings",
            "PATCH",
            {
                "site_name": "TRADE HUB Haïti",
                "announcement": "Nouvelle saison",
                "hero_eyebrow": "Le commerce local",
                "hero_title": "Découvrez nos produits",
                "hero_description": "Des offres choisies près de chez vous.",
                "hero_cta_label": "Voir le marché",
                "hero_link_label": "Parcourir les boutiques",
            },
        )
        status = self.request(self.client, "/api/status")
        self.assertEqual(status["settings"]["site_name"], "TRADE HUB Haïti")
        self.assertEqual(status["settings"]["announcement"], "Nouvelle saison")
        self.assertEqual(status["settings"]["hero_eyebrow"], "Le commerce local")
        self.assertEqual(status["settings"]["hero_title"], "Découvrez nos produits")
        self.assertEqual(status["settings"]["hero_description"], "Des offres choisies près de chez vous.")
        self.assertEqual(status["settings"]["hero_cta_label"], "Voir le marché")
        self.assertEqual(status["settings"]["hero_link_label"], "Parcourir les boutiques")
        self.request(self.seller, "/api/products/" + str(product_id), "DELETE")
        self.assertEqual(self.request(self.client, "/api/products")["products"], [])

    def test_customer_session_persistence_vendor_promotion_and_owner_recovery(self):
        self.request(
            self.owner,
            "/api/setup",
            "POST",
            {
                "setup_key": server.BOOTSTRAP_SECRET,
                "username": self.OWNER_USERNAME,
                "password": self.OWNER_PASSWORD,
            },
            201,
        )
        self.request(
            self.owner,
            "/api/login",
            "POST",
            {"username": self.OWNER_USERNAME, "password": self.OWNER_PASSWORD},
        )
        customer = self.request(
            self.client,
            "/api/register",
            "POST",
            {"username": "client-promote", "password": "customer-password-2026"},
            200,
        )
        self.assertEqual(customer["user"]["role"], "customer")
        self.assertEqual(self.request(self.client, "/api/me")["user"]["username"], "client-promote")
        self.assertEqual(
            self.request(self.owner, "/api/admin/users/search?username=client-promote")["user"]["username"],
            "client-promote",
        )
        self.request(
            self.owner,
            "/api/admin/users/promote",
            "POST",
            {"username": "client-promote", "store_name": "Boutique Client"},
        )
        self.request(
            self.client,
            "/api/login",
            "POST",
            {"username": "client-promote", "password": "customer-password-2026"},
        )
        self.assertEqual(self.request(self.client, "/api/me")["user"]["role"], "seller")
        self.request(self.client, "/api/seller/products", expected=200)
        self.request(self.client, "/api/logout", "POST")
        self.request(self.client, "/api/me", expected=401)

        restarted = self.new_client()
        restarted_server = server.TradeHubServer(("127.0.0.1", 0), server.TradeHubHandler)
        restarted_thread = threading.Thread(target=restarted_server.serve_forever, daemon=True)
        restarted_thread.start()
        try:
            restarted_url = "http://127.0.0.1:" + str(restarted_server.server_address[1])
            restarted_request = Request(
                restarted_url + "/api/login",
                data=json.dumps(
                    {"username": self.OWNER_USERNAME, "password": self.OWNER_PASSWORD}
                ).encode("utf-8"),
                method="POST",
                headers={"Content-Type": "application/json"},
            )
            restarted_opener = build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))
            try:
                response = restarted_opener.open(restarted_request, timeout=5)
                result = json.loads(response.read().decode("utf-8"))
            except HTTPError as error:
                result = json.loads(error.read().decode("utf-8"))
            self.assertEqual(response.status, 200)
            self.assertEqual(result["user"]["role"], "owner")
            self.assertEqual(restarted_opener.open(Request(restarted_url + "/api/me", method="GET")).status, 200)
        finally:
            restarted_server.shutdown()
            restarted_server.server_close()
            restarted_thread.join(timeout=2)

    def test_public_realtime_stream(self):
        connection = http.client.HTTPConnection("127.0.0.1", self.httpd.server_address[1], timeout=2)
        connection.request("GET", "/api/events")
        response = connection.getresponse()
        self.assertEqual(response.status, 200)
        response.readline()
        response.readline()
        server.publish("catalog")
        packet = response.readline().decode("utf-8").removeprefix("data: ").strip()
        self.assertEqual(json.loads(packet)["event"], "catalog")
        connection.close()

    def test_public_assistant_messages_and_owner_inbox_permissions(self):
        self.request(
            self.owner,
            "/api/setup",
            "POST",
            {
                "setup_key": server.BOOTSTRAP_SECRET,
                "username": self.OWNER_USERNAME,
                "password": self.OWNER_PASSWORD,
            },
            201,
        )
        self.request(
            self.owner,
            "/api/login",
            "POST",
            {"username": self.OWNER_USERNAME, "password": self.OWNER_PASSWORD},
        )
        self.request(
            self.client,
            "/api/contact-owner",
            "POST",
            {
                "name": "Visiteur <test>",
                "contact": "visitor@example.test",
                "message": "Bonjour, j’ai besoin d’aide.",
            },
            201,
        )
        self.request(self.client, "/api/admin/messages", expected=401)

        inbox = self.request(self.owner, "/api/admin/messages")
        self.assertEqual(len(inbox["messages"]), 1)
        message = inbox["messages"][0]
        self.assertEqual(message["sender_name"], "Visiteur <test>")
        self.assertEqual(message["reply_contact"], "visitor@example.test")
        self.assertEqual(message["message"], "Bonjour, j’ai besoin d’aide.")
        self.assertEqual(message["status"], "new")

        self.request(
            self.owner,
            "/api/admin/messages/" + str(message["id"]),
            "PATCH",
            {"status": "read"},
        )
        updated = self.request(self.owner, "/api/admin/messages")["messages"][0]
        self.assertEqual(updated["status"], "read")

    def test_owner_inbox_returns_only_the_200_most_recent_messages(self):
        self.request(
            self.owner,
            "/api/setup",
            "POST",
            {
                "setup_key": server.BOOTSTRAP_SECRET,
                "username": self.OWNER_USERNAME,
                "password": self.OWNER_PASSWORD,
            },
            201,
        )
        self.request(
            self.owner,
            "/api/login",
            "POST",
            {"username": self.OWNER_USERNAME, "password": self.OWNER_PASSWORD},
        )
        with server.connect_db() as db:
            db.executemany(
                """INSERT INTO owner_messages(sender_name,message,created_at)
                   VALUES (?,?,?)""",
                [
                    ("Visiteur " + str(index), "Message " + str(index), index)
                    for index in range(205)
                ],
            )

        messages = self.request(self.owner, "/api/admin/messages")["messages"]
        self.assertEqual(len(messages), 200)
        self.assertEqual(messages[0]["sender_name"], "Visiteur 204")
        self.assertEqual(messages[-1]["sender_name"], "Visiteur 5")


if __name__ == "__main__":
    unittest.main()