"""
Tor Bridge Master - параллельный сканер мостов obfs4 с HTML отчётом.

Проверка моста двухступенчатая:
  1. Быстрый TCP-connect (даёт честную задержку RTT и отсекает закрытые порты).
  2. Реальный obfs4-хендшейк через локальный tor + obfs4proxy.

Если tor/obfs4proxy не найдены, шаг 2 пропускается с предупреждением
(остаётся только TCP-проверка), чтобы инструмент оставался работоспособным.
"""

import re
import os
import sys
import json
import html
import time
import shutil
import socket
import logging
import argparse
import tempfile
import threading
import subprocess
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Tuple, Optional
from dataclasses import dataclass

# Попытка импорта tqdm для красивого прогресс-бара
try:
    from tqdm import tqdm
    TQDM_AVAILABLE = True
except ImportError:
    TQDM_AVAILABLE = False
    print("[!] tqdm не установлен. Установите: pip install tqdm")

    # Простой прогресс-бар на случай отсутствия tqdm
    class SimpleTqdm:
        def __init__(self, total, desc="Progress", unit=""):
            self.total = total
            self.desc = desc
            self.n = 0

        def update(self, n=1):
            self.n += n
            print(f"\r{self.desc}: {self.n}/{self.total}", end="", flush=True)

        def close(self):
            print()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.close()

    tqdm = SimpleTqdm


# ── Значения по умолчанию ──
DEFAULT_MAX_WORKERS = 10
DEFAULT_TOP_LIMIT = 16
DEFAULT_TCP_TIMEOUT = 5      # сек на TCP-connect
DEFAULT_OBFS4_TIMEOUT = 30   # сек на obfs4-хендшейк (bootstrap tor)
TCP_PROBES = 2               # число замеров RTT (берётся минимум)

# Строка obfs4-моста: obfs4 IP:PORT FINGERPRINT cert=... iat-mode=0|1|2
BRIDGE_RE = re.compile(
    r"obfs4 (\d+\.\d+\.\d+\.\d+):(\d+) ([0-9a-fA-F]+) cert=(\S+) iat-mode=([0-2])"
)


@dataclass
class Bridge:
    """Мост obfs4."""
    ip: str
    port: int
    sha: str
    cert: str
    im: int
    key: str
    latency: Optional[float] = None   # в секундах (TCP RTT), если жив
    alive: bool = False

    def line(self) -> str:
        """Каноническая строка моста obfs4."""
        return f"obfs4 {self.ip}:{self.port} {self.sha} cert={self.cert} iat-mode={self.im}"


def find_executable(name: str, extra_paths: List[str]) -> Optional[str]:
    """Ищет исполняемый файл в PATH, затем в типичных местах установки."""
    found = shutil.which(name)
    if found:
        return found
    for path in extra_paths:
        if os.path.isfile(path):
            return path
    return None


def find_tor() -> Optional[str]:
    """Путь к tor.exe (PATH или установка Tor Browser)."""
    candidates = [
        os.path.expandvars(r"%USERPROFILE%\Desktop\Tor Browser\Browser\TorBrowser\Tor\tor.exe"),
        os.path.expandvars(r"%LOCALAPPDATA%\Tor Browser\Browser\TorBrowser\Tor\tor.exe"),
        r"C:\Program Files\Tor Browser\Browser\TorBrowser\Tor\tor.exe",
    ]
    return find_executable("tor", candidates)


def find_obfs4proxy() -> Optional[str]:
    """Путь к obfs4proxy.exe (PATH или Pluggable Transports Tor Browser)."""
    pt = r"Browser\TorBrowser\Tor\PluggableTransports\obfs4proxy.exe"
    candidates = [
        os.path.expandvars(rf"%USERPROFILE%\Desktop\Tor Browser\{pt}"),
        os.path.expandvars(rf"%LOCALAPPDATA%\Tor Browser\{pt}"),
        rf"C:\Program Files\Tor Browser\{pt}",
    ]
    return find_executable("obfs4proxy", candidates)


class BridgeScanner:
    """Сканер мостов с параллельной проверкой."""

    def __init__(self, work_dir: Optional[str] = None,
                 max_workers: int = DEFAULT_MAX_WORKERS,
                 top_limit: int = DEFAULT_TOP_LIMIT,
                 tcp_timeout: int = DEFAULT_TCP_TIMEOUT,
                 obfs4_timeout: int = DEFAULT_OBFS4_TIMEOUT,
                 verify_obfs4: bool = True):
        # Корень проекта = родительская папка src (где лежит этот файл)
        script_dir = os.path.dirname(os.path.abspath(__file__))
        if work_dir is None:
            work_dir = os.path.dirname(script_dir)
        self.work_dir = work_dir
        self.max_workers = max_workers
        self.top_limit = top_limit
        self.tcp_timeout = tcp_timeout
        self.obfs4_timeout = obfs4_timeout

        # Пути к файлам
        self.br_file = os.path.join(work_dir, 'obfs4_tested.txt')
        self.template_file = os.path.join(script_dir, 'report_template.html')
        self.html_output = os.path.join(work_dir, 'Best_Bridges.html')

        self._setup_logging()

        # Инструменты для реальной obfs4-проверки
        self.tor_path = find_tor() if verify_obfs4 else None
        self.obfs4proxy_path = find_obfs4proxy() if verify_obfs4 else None
        self.verify_obfs4 = bool(self.tor_path and self.obfs4proxy_path)

        if verify_obfs4 and not self.verify_obfs4:
            missing = []
            if not self.tor_path:
                missing.append("tor")
            if not self.obfs4proxy_path:
                missing.append("obfs4proxy")
            self.logger.warning(
                f"Не найдены: {', '.join(missing)}. obfs4-хендшейк пропускается, "
                f"используется только TCP-проверка (порт открыт + задержка)."
            )
        elif self.verify_obfs4:
            self.logger.info(f"obfs4-проверка включена (tor: {self.tor_path})")

        self.logger.info(f"Сканер инициализирован. Рабочая папка: {work_dir}")
        self.logger.info(f"Максимум потоков: {max_workers}")

    def _setup_logging(self):
        """Настройка логирования только в консоль."""
        os.makedirs(self.work_dir, exist_ok=True)
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[logging.StreamHandler(sys.stdout)]
        )
        self.logger = logging.getLogger('BridgeScanner')

    def load_bridges_from_file(self) -> List[Bridge]:
        """Загружает мосты из файла obfs4_tested.txt."""
        if not os.path.exists(self.br_file):
            self.logger.error(f"Файл не найден: {self.br_file}")
            self.logger.error("Сначала скачайте список мостов (Start.ps1)!")
            sys.exit(1)

        bridges: List[Bridge] = []
        seen_keys = set()

        with open(self.br_file, 'r', encoding='utf-8') as f:
            for line in f:
                m = BRIDGE_RE.match(line.strip())
                if not m:
                    continue
                ip, port, sha, cert, im = (
                    m.group(1), int(m.group(2)), m.group(3), m.group(4), int(m.group(5))
                )
                key = f"{ip}:{port}"
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                bridges.append(Bridge(ip=ip, port=port, sha=sha, cert=cert, im=im, key=key))

        self.logger.info(f"Загружено мостов из файла: {len(bridges)}")
        return bridges

    def tcp_latency(self, bridge: Bridge) -> Optional[float]:
        """
        Измеряет TCP RTT до моста. Возвращает минимальную задержку (сек)
        из нескольких попыток или None, если порт недоступен.
        """
        best: Optional[float] = None
        for _ in range(TCP_PROBES):
            start = time.perf_counter()
            try:
                with socket.create_connection((bridge.ip, bridge.port), timeout=self.tcp_timeout):
                    elapsed = time.perf_counter() - start
            except OSError:
                continue
            if best is None or elapsed < best:
                best = elapsed
        return best

    def verify_obfs4_handshake(self, bridge: Bridge) -> bool:
        """
        Поднимает временный tor с единственным мостом и ждёт Bootstrapped 100%.
        Возвращает True, если obfs4-хендшейк и bootstrap прошли успешно.
        """
        tmpdir = tempfile.mkdtemp(prefix="tbm_")
        torrc = os.path.join(tmpdir, "torrc")
        try:
            with open(torrc, 'w', encoding='utf-8') as f:
                f.write("SocksPort auto\n")
                f.write("ControlPort 0\n")
                f.write(f"DataDirectory {tmpdir}\n")
                f.write("UseBridges 1\n")
                f.write(f"ClientTransportPlugin obfs4 exec {self.obfs4proxy_path}\n")
                f.write(f"Bridge {bridge.line()}\n")

            proc = subprocess.Popen(
                [self.tor_path, "-f", torrc],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding='utf-8',
                errors='replace',
            )

            # Сторож: убиваем tor по таймауту, чтобы readline не висел вечно
            killer = threading.Timer(self.obfs4_timeout, proc.kill)
            killer.start()
            success = False
            try:
                for out_line in proc.stdout:
                    if "Bootstrapped 100%" in out_line:
                        success = True
                        break
                    if "Bootstrapped 100" in out_line:  # на случай форматов вида "100 (done)"
                        success = True
                        break
            finally:
                killer.cancel()
                proc.kill()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    pass
            return success
        except Exception as e:
            self.logger.debug(f"obfs4-проверка {bridge.key} не удалась: {e}")
            return False
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def check_bridge(self, bridge: Bridge) -> Tuple[Bridge, Optional[float]]:
        """
        Полная проверка моста.
        Возвращает (bridge, latency_seconds) или (bridge, None) если мост не годен.
        """
        latency = self.tcp_latency(bridge)
        if latency is None:
            return bridge, None
        if self.verify_obfs4 and not self.verify_obfs4_handshake(bridge):
            return bridge, None
        return bridge, latency

    def scan_bridges(self, bridges: List[Bridge]) -> List[Bridge]:
        """Параллельное сканирование мостов с прогресс-баром."""
        alive_bridges: List[Bridge] = []
        total = len(bridges)
        mode = "obfs4-хендшейк" if self.verify_obfs4 else "TCP"
        self.logger.info(
            f"Сканирование {total} мостов в {self.max_workers} потоков ({mode})..."
        )

        with tqdm(total=total, desc="Сканирование", unit="мост") as pbar:
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                future_to_bridge = {
                    executor.submit(self.check_bridge, b): b for b in bridges
                }
                try:
                    for future in as_completed(future_to_bridge):
                        bridge = future_to_bridge[future]
                        try:
                            bridge, latency = future.result()
                            if latency is not None:
                                bridge.alive = True
                                bridge.latency = latency
                                alive_bridges.append(bridge)
                                self.logger.debug(f"✓ {bridge.key} - {latency:.3f}s")
                            else:
                                self.logger.debug(f"✗ {bridge.key} - dead")
                        except Exception as e:
                            self.logger.error(f"Ошибка при проверке {bridge.key}: {e}")
                        pbar.update(1)
                except KeyboardInterrupt:
                    self.logger.warning("Прерывание пользователем. Завершаем сканирование...")
                    executor.shutdown(wait=False, cancel_futures=True)
                    raise

        self.logger.info(f"Сканирование завершено. Живых мостов: {len(alive_bridges)}")
        return alive_bridges

    @staticmethod
    def sort_by_latency(bridges: List[Bridge]) -> List[Bridge]:
        """Живые мосты, отсортированные по возрастанию задержки."""
        return sorted(bridges, key=lambda b: b.latency if b.latency is not None else float('inf'))

    @staticmethod
    def _latency_class(sec: float) -> str:
        return "fast" if sec < 1 else ("medium" if sec < 3 else "slow")

    def _render_row(self, idx: int, bridge: Bridge, ranked: bool) -> str:
        """Одна строка таблицы. Все данные моста экранируются."""
        ip = html.escape(bridge.ip)
        port = html.escape(str(bridge.port))
        sha = html.escape(bridge.sha)
        cert = html.escape(bridge.cert)
        im = html.escape(str(bridge.im))
        sec = bridge.latency
        cls = self._latency_class(sec)
        attr = html.escape(bridge.line(), quote=True)

        if ranked and idx <= 3:
            rank_html = f'<span class="rank-top rank-{idx}">{idx}</span>'
        else:
            rank_html = str(idx)

        return (
            "                    <tr>\n"
            f"                        <td>{rank_html}</td>\n"
            f'                        <td class="bridge-cell"><div class="bridge-code">'
            f'<span class="proto">obfs4</span> <span class="ip">{ip}:{port}</span> '
            f"{sha} cert={cert} iat-mode={im}</div></td>\n"
            f'                        <td><span class="latency-badge {cls}">'
            f'<span class="dot dot-{cls}"></span>{sec:.3f}s</span></td>\n'
            f'                        <td><button class="copy-btn" data-bridge="{attr}" '
            'title="Copy">⧉</button></td>\n'
            "                    </tr>"
        )

    def export_html(self, best_bridges: List[Bridge], all_alive: List[Bridge]):
        """Генерирует HTML отчёт из шаблона report_template.html."""
        if not os.path.exists(self.template_file):
            self.logger.error(f"Шаблон отчёта не найден: {self.template_file}")
            return

        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        best_ms = f"{best_bridges[0].latency * 1000:.0f}" if best_bridges else "—"
        avg_ms = (
            f"{(sum(b.latency for b in all_alive) / len(all_alive) * 1000):.0f}"
            if all_alive else "—"
        )
        n_top = len(best_bridges)

        top_rows = "\n".join(
            self._render_row(i, b, ranked=True) for i, b in enumerate(best_bridges, 1)
        )
        all_rows = "\n".join(
            self._render_row(i, b, ranked=False) for i, b in enumerate(all_alive, 1)
        )

        # JS-массив строк через json.dumps — корректно экранирует кавычки и слеши.
        # Дополнительно нейтрализуем "</" чтобы не закрыть тег <script> раньше времени.
        top_json = json.dumps([b.line() for b in best_bridges]).replace("</", "<\\/")

        with open(self.template_file, 'r', encoding='utf-8') as f:
            html_content = f.read()

        replacements = {
            "__NOW__": now,
            "__ALIVE_COUNT__": str(len(all_alive)),
            "__BEST_MS__": best_ms,
            "__AVG_MS__": avg_ms,
            "__N_TOP__": str(n_top),
            "__TOP_ROWS__": top_rows,
            "__ALL_ROWS__": all_rows,
            "__TOP_BRIDGES_JSON__": top_json,
        }
        for token, value in replacements.items():
            html_content = html_content.replace(token, value)

        try:
            with open(self.html_output, 'w', encoding='utf-8') as f:
                f.write(html_content)
            self.logger.info(f"HTML отчёт сохранён: {self.html_output}")
        except Exception as e:
            self.logger.error(f"Ошибка сохранения HTML: {e}")


def _force_utf8_stdout():
    """Переводит stdout/stderr в UTF-8, чтобы кириллица и символы (✓/✗) не
    падали на легаси-консоли Windows (cp1251)."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding='utf-8')
        except (AttributeError, ValueError):
            pass


def main():
    _force_utf8_stdout()
    parser = argparse.ArgumentParser(description="Tor Bridge Master - сканер obfs4 мостов")
    parser.add_argument("--max-workers", type=int, default=DEFAULT_MAX_WORKERS,
                        help=f"Количество потоков (по умолч. {DEFAULT_MAX_WORKERS})")
    parser.add_argument("--top", type=int, default=DEFAULT_TOP_LIMIT,
                        help=f"Размер топа быстрых мостов (по умолч. {DEFAULT_TOP_LIMIT})")
    parser.add_argument("--tcp-timeout", type=int, default=DEFAULT_TCP_TIMEOUT,
                        help=f"Таймаут TCP-connect, сек (по умолч. {DEFAULT_TCP_TIMEOUT})")
    parser.add_argument("--obfs4-timeout", type=int, default=DEFAULT_OBFS4_TIMEOUT,
                        help=f"Таймаут obfs4-хендшейка, сек (по умолч. {DEFAULT_OBFS4_TIMEOUT})")
    parser.add_argument("--no-verify", action="store_true",
                        help="Пропустить obfs4-хендшейк, только TCP-проверка (быстрее)")
    parser.add_argument("--work-dir", type=str, default=None, help="Рабочая папка")
    args = parser.parse_args()

    scanner = BridgeScanner(
        work_dir=args.work_dir,
        max_workers=args.max_workers,
        top_limit=args.top,
        tcp_timeout=args.tcp_timeout,
        obfs4_timeout=args.obfs4_timeout,
        verify_obfs4=not args.no_verify,
    )

    try:
        bridges = scanner.load_bridges_from_file()
        alive = scanner.scan_bridges(bridges)

        sorted_alive = scanner.sort_by_latency(alive)
        best = sorted_alive[:scanner.top_limit]

        scanner.export_html(best, sorted_alive)

    except KeyboardInterrupt:
        scanner.logger.warning("\nПрерывание пользователем.")
    except Exception as e:
        scanner.logger.error(f"Неожиданная ошибка: {e}", exc_info=True)
    finally:
        # Закрываем хендлеры логирования
        for handler in logging.root.handlers[:]:
            handler.close()
            logging.root.removeHandler(handler)

        # Удаление временного файла со списком мостов
        try:
            if os.path.exists(scanner.br_file):
                os.remove(scanner.br_file)
                print(f"[✓] Удалён временный файл: {os.path.basename(scanner.br_file)}")
        except Exception as e:
            print(f"[!] Не удалось удалить {scanner.br_file}: {e}")

        print(f"\n{'=' * 60}")
        print("✅ Сканирование завершено!")
        print(f"📄 HTML отчёт: {scanner.html_output}")
        print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
