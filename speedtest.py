import argparse
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

CHUNK_SIZE = 64 * 1024
HEADERS = {
    "User-Agent": "speedtest-cli/1.0",
    "Accept-Encoding": "identity",
    "Cache-Control": "no-cache",
}


@dataclass(frozen=True)
class Attempt:
    seconds: float
    size: int


@dataclass(frozen=True)
class Summary:
    attempts: list[Attempt]

    @property
    def total_bytes(self) -> int:
        return sum(a.size for a in self.attempts)

    @property
    def total_seconds(self) -> float:
        return sum(a.seconds for a in self.attempts)

    @property
    def average_seconds(self) -> float:
        return self.total_seconds / len(self.attempts)

    @property
    def megabits_per_second(self) -> float:
        return self.total_bytes * 8 / self.total_seconds / 1_000_000

    @property
    def megabytes_per_second(self) -> float:
        return self.total_bytes / self.total_seconds / 1_000_000


def download(url: str, timeout: float) -> Attempt:
    request = urllib.request.Request(url, headers=HEADERS)
    started = time.perf_counter()
    size = 0
    with urllib.request.urlopen(request, timeout=timeout) as response:
        while chunk := response.read(CHUNK_SIZE):
            size += len(chunk)
    return Attempt(seconds=time.perf_counter() - started, size=size)


def measure(url: str, count: int, timeout: float, on_attempt=None) -> Summary:
    attempts = []
    for number in range(1, count + 1):
        attempt = download(url, timeout)
        attempts.append(attempt)
        if on_attempt:
            on_attempt(number, attempt)
    return Summary(attempts)


def format_bytes(size: int) -> str:
    for unit in ("Б", "КБ", "МБ"):
        if size < 1000:
            return f"{size:.0f} {unit}" if unit == "Б" else f"{size:.2f} {unit}"
        size /= 1000
    return f"{size:.2f} ГБ"


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Замер скорости скачивания по одному адресу")
    parser.add_argument("url", help="адрес файла, например большой картинки")
    parser.add_argument("-n", "--count", type=int, default=10, help="число запросов (по умолчанию 10)")
    parser.add_argument("-t", "--timeout", type=float, default=30.0, help="тайм-аут одного запроса в секундах (по умолчанию 30)")
    args = parser.parse_args(argv)
    if not args.url.startswith(("http://", "https://")):
        parser.error("адрес должен начинаться с http:// или https://")
    if args.count < 1:
        parser.error("число запросов должно быть не меньше 1")
    if args.timeout <= 0:
        parser.error("тайм-аут должен быть больше нуля")
    return args


def main(argv=None) -> int:
    args = parse_args(argv)

    def report(number, attempt):
        print(f"  запрос {number:>2}: {attempt.seconds:.3f} с, {format_bytes(attempt.size)}", flush=True)

    print(f"Скачиваю {args.url} {args.count} раз(а) подряд", flush=True)
    try:
        summary = measure(args.url, args.count, args.timeout, on_attempt=report)
    except urllib.error.HTTPError as exc:
        print(f"Ошибка: сервер ответил {exc.code} {exc.reason}", file=sys.stderr)
        return 1
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        reason = getattr(exc, "reason", exc)
        print(f"Ошибка соединения: {reason}", file=sys.stderr)
        return 1

    if summary.total_bytes == 0:
        print("Сервер вернул пустой ответ, скорость посчитать нельзя", file=sys.stderr)
        return 1

    print()
    print(f"Среднее время запроса: {summary.average_seconds:.3f} с")
    print(f"Всего скачано: {format_bytes(summary.total_bytes)} ({summary.total_bytes} байт)")
    print(f"Скорость: {summary.megabits_per_second:.2f} Мбит/с ({summary.megabytes_per_second:.2f} МБ/с)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
