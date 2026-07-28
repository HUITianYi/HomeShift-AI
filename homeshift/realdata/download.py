"""下载与缓存工具（只用标准库）。

设计要点（针对"用户不会处理数据"这个前提）：
- 多镜像自动切换：一个链接挂了自动换下一个；
- 断点续传：已下载完整的文件直接复用，中断的 .part 文件会续传；
- 进度条：大文件下载不会让人以为程序卡死；
- 明确的错误提示：把"网络不通/被墙/链接失效"分别说清楚，并给出手工下载指引。
"""

from __future__ import annotations

import shutil
import sys
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

USER_AGENT = "HomeShiftAI/1.0 (course project; python-urllib)"


class DownloadError(RuntimeError):
    pass


def _human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}TB"


def _progress(done: int, total: int, start: float, label: str) -> None:
    if not sys.stdout.isatty():
        return
    elapsed = max(time.time() - start, 1e-6)
    speed = done / elapsed
    if total > 0:
        pct = done / total * 100
        bar_len = 24
        filled = int(bar_len * done / total)
        bar = "#" * filled + "-" * (bar_len - filled)
        sys.stdout.write(
            f"\r  {label} [{bar}] {pct:5.1f}%  {_human(done)}/{_human(total)}  {_human(speed)}/s"
        )
    else:
        sys.stdout.write(f"\r  {label} {_human(done)}  {_human(speed)}/s")
    sys.stdout.flush()


def download_file(
    urls: list[str],
    dest: Path,
    timeout: int = 600,
    label: str = "下载中",
) -> Path:
    """依次尝试多个 URL，下载到 dest。已存在且非空则直接复用。"""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)

    if dest.exists() and dest.stat().st_size > 0:
        print(f"  已缓存，跳过下载：{dest.name}（{_human(dest.stat().st_size)}）")
        return dest

    part = dest.with_suffix(dest.suffix + ".part")
    errors: list[str] = []

    for index, url in enumerate(urls, start=1):
        resume_from = part.stat().st_size if part.exists() else 0
        headers = {"User-Agent": USER_AGENT}
        if resume_from:
            headers["Range"] = f"bytes={resume_from}-"
        request = urllib.request.Request(url, headers=headers)

        try:
            print(f"  尝试镜像 {index}/{len(urls)}：{url[:88]}")
            with urllib.request.urlopen(request, timeout=timeout) as resp:
                total = int(resp.headers.get("Content-Length") or 0)
                if resume_from and resp.status == 206:
                    total += resume_from
                    mode = "ab"
                    done = resume_from
                    print(f"  断点续传，从 {_human(resume_from)} 继续")
                else:
                    mode = "wb"
                    done = 0
                start = time.time()
                with open(part, mode) as f:
                    while True:
                        chunk = resp.read(1 << 16)
                        if not chunk:
                            break
                        f.write(chunk)
                        done += len(chunk)
                        _progress(done, total, start, label)
            if sys.stdout.isatty():
                sys.stdout.write("\n")
            if part.stat().st_size == 0:
                raise DownloadError("下载到 0 字节")
            part.replace(dest)
            print(f"  完成：{dest.name}（{_human(dest.stat().st_size)}）")
            return dest

        except urllib.error.HTTPError as exc:
            errors.append(f"{url} -> HTTP {exc.code}")
            print(f"  失败：HTTP {exc.code}")
        except urllib.error.URLError as exc:
            errors.append(f"{url} -> {exc.reason}")
            print(f"  失败：{exc.reason}")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{url} -> {exc}")
            print(f"  失败：{exc}")

    detail = "\n    ".join(errors)
    raise DownloadError(
        "所有镜像都下载失败：\n    " + detail + "\n\n"
        "可能原因与对策：\n"
        "  1) 网络需要代理：先设置 HTTPS_PROXY 环境变量再重试\n"
        "     macOS/Linux: export HTTPS_PROXY=http://127.0.0.1:7890\n"
        "     Windows PS : $env:HTTPS_PROXY=\"http://127.0.0.1:7890\"\n"
        "  2) 链接已失效：手工下载后放到 " + str(dest) + " 再重新运行本脚本\n"
        "  3) 学校网络限制：换个网络环境，或改用 --dataset csv 导入本地文件"
    )


def extract_member(archive: Path, member: str, out_dir: Path) -> Path:
    """从 zip 里解出指定文件；member 允许只写文件名（自动在压缩包内查找）。"""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / Path(member).name

    if target.exists() and target.stat().st_size > 0:
        print(f"  已解压，跳过：{target.name}（{_human(target.stat().st_size)}）")
        return target

    if not zipfile.is_zipfile(archive):
        raise DownloadError(
            f"{archive.name} 不是有效的 zip 文件（可能下载到了错误页面）。"
            f"请删除它后重试：{archive}"
        )

    with zipfile.ZipFile(archive) as zf:
        names = zf.namelist()
        match = next((n for n in names if Path(n).name == Path(member).name), None)
        if match is None:
            raise DownloadError(
                f"压缩包里找不到 {member}。压缩包内容：{names[:10]}"
            )
        print(f"  解压 {match} ...")
        with zf.open(match) as src, open(target, "wb") as dst:
            shutil.copyfileobj(src, dst, length=1 << 20)

    print(f"  完成：{target.name}（{_human(target.stat().st_size)}）")
    return target


def fetch_json(url: str, timeout: int = 120) -> dict:
    """GET 一个 JSON 接口（用于 Open-Meteo / data.gov.sg）。"""
    import json

    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8", errors="replace")[:400]
        except Exception:
            pass
        raise DownloadError(f"请求失败 HTTP {exc.code}：{url}\n{body}") from exc
    except urllib.error.URLError as exc:
        raise DownloadError(
            f"无法连接：{url}\n原因：{exc.reason}\n"
            "如果在需要代理的网络下，请先设置 HTTPS_PROXY 环境变量。"
        ) from exc
