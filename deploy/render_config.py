"""Generate the two Nginx configurations from a validated domain name."""
import argparse
import ipaddress
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def validate_domain(value):
    domain = value.strip().lower().rstrip(".")
    if len(domain) > 253 or "." not in domain:
        raise ValueError("请输入完整ASCII域名，例如oa.example.com，不带协议和路径")
    try:
        ipaddress.ip_address(domain)
    except ValueError:
        pass
    else:
        raise ValueError("本教程使用域名证书，请输入域名而不是IP")
    if any(not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", part) for part in domain.split(".")):
        raise ValueError("域名格式不正确；国际化域名请先使用注册商提供的ASCII形式")
    return domain


def render(domain, root=ROOT):
    domain = validate_domain(domain)
    for name in ("bootstrap", "cloud"):
        template = root / "deploy/nginx" / f"{name}.conf.template"
        output = template.with_suffix("")
        text = template.read_text(encoding="utf-8").replace("__DOMAIN__", domain)
        output.write_text(text, encoding="utf-8", newline="\n")
    return domain


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--domain", required=True)
    args = parser.parse_args()
    try:
        print("Generated configuration for " + render(args.domain))
    except ValueError as error:
        parser.error(str(error))
