"""测试 MyAIPlanner 项目依赖的服务器连通性"""
import socket
import sys
import io

# Windows 控制台 UTF-8 输出
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

# 项目依赖的外部服务
SERVERS = [
    ("Google OAuth", "https://accounts.google.com", 443),
    ("Google API", "https://www.googleapis.com", 443),
    ("OpenAI API", "https://api.openai.com", 443),
    ("GitHub", "https://github.com", 443),
]


def test_socket(host: str, port: int, timeout: float = 5.0) -> tuple[bool, str]:
    """TCP 端口连通性测试"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect((host, port))
        s.close()
        return True, "连接成功"
    except socket.timeout:
        return False, "连接超时"
    except socket.gaierror as e:
        return False, f"DNS 解析失败: {e}"
    except OSError as e:
        return False, str(e)


def test_http(url: str, timeout: float = 10.0) -> tuple[bool, str]:
    """HTTP(S) 请求测试"""
    try:
        req = Request(url, headers={"User-Agent": "MyAIPlanner-Connectivity-Test/1.0"})
        with urlopen(req, timeout=timeout) as resp:
            code = resp.getcode()
            return True, f"HTTP {code}"
    except HTTPError as e:
        return True, f"HTTP {e.code} (服务可达)"
    except URLError as e:
        return False, str(e.reason) if e.reason else "连接失败"
    except TimeoutError:
        return False, "请求超时"
    except Exception as e:
        return False, str(e)


def main():
    print("=" * 60)
    print("MyAIPlanner 服务器连通性测试")
    print("=" * 60)

    all_ok = True
    for name, url, port in SERVERS:
        host = url.replace("https://", "").replace("http://", "").split("/")[0]
        print(f"\n【{name}】 {url}")
        print("-" * 50)

        # 1. TCP 端口测试
        ok1, msg1 = test_socket(host, port)
        status1 = "✓" if ok1 else "✗"
        print(f"  TCP {port}: {status1} {msg1}")

        # 2. HTTP 请求测试
        ok2, msg2 = test_http(url)
        status2 = "✓" if ok2 else "✗"
        print(f"  HTTP:  {status2} {msg2}")

        # HTTP 成功即视为服务可用（应用通过 HTTP 访问）
        if not ok2:
            all_ok = False

    print("\n" + "=" * 60)
    if all_ok:
        print("✓ 所有服务器 HTTP 连通性正常，应用可正常使用")
    else:
        print("✗ 部分服务器无法连通，请检查网络/代理/防火墙")
        print("  提示：若使用代理，请设置 HTTP_PROXY/HTTPS_PROXY 环境变量")
    print("=" * 60)
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
