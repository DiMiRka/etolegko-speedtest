import contextlib
import io
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import speedtest

PAYLOAD = b"x" * 300_000


class Handler(BaseHTTPRequestHandler):
    hits = 0

    def do_GET(self):
        Handler.hits += 1
        if self.path == "/missing":
            self.send_error(404)
            return
        body = b"" if self.path == "/empty" else PAYLOAD
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


class SpeedtestTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        Handler.hits = 0

    def run_main(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = speedtest.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_makes_ten_sequential_requests_and_counts_bytes(self):
        summary = speedtest.measure(f"{self.base}/file", count=10, timeout=5)
        self.assertEqual(Handler.hits, 10)
        self.assertEqual(len(summary.attempts), 10)
        self.assertEqual(summary.total_bytes, 10 * len(PAYLOAD))
        self.assertTrue(all(a.size == len(PAYLOAD) for a in summary.attempts))

    def test_speed_math(self):
        summary = speedtest.Summary([speedtest.Attempt(1.0, 1_000_000), speedtest.Attempt(3.0, 4_000_000)])
        self.assertEqual(summary.average_seconds, 2.0)
        self.assertEqual(summary.megabytes_per_second, 1.25)
        self.assertEqual(summary.megabits_per_second, 10.0)

    def test_cli_prints_summary(self):
        code, out, _ = self.run_main(f"{self.base}/file", "-n", "3")
        self.assertEqual(code, 0)
        self.assertIn("Среднее время запроса", out)
        self.assertIn("Мбит/с", out)
        self.assertIn("900000 байт", out)

    def test_http_error_returns_nonzero(self):
        code, _, err = self.run_main(f"{self.base}/missing")
        self.assertEqual(code, 1)
        self.assertIn("404", err)
        self.assertEqual(Handler.hits, 1)

    def test_connection_error_returns_nonzero(self):
        code, _, err = self.run_main("http://127.0.0.1:1/file", "-n", "1", "-t", "2")
        self.assertEqual(code, 1)
        self.assertIn("Ошибка соединения", err)

    def test_empty_response_is_reported(self):
        code, _, err = self.run_main(f"{self.base}/empty", "-n", "2")
        self.assertEqual(code, 1)
        self.assertIn("пустой ответ", err)

    def test_rejects_bad_arguments(self):
        for argv in (["ftp://example.com/file"], ["http://example.com", "-n", "0"]):
            with self.subTest(argv=argv), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    speedtest.parse_args(argv)


if __name__ == "__main__":
    unittest.main()
