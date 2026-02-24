import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from ..utils import get_logger

logger = get_logger("cloudflare_pages")


@dataclass
class CloudflarePagesBuild:
    command: str = "python main.py"
    output_dir: str = "data/output"
    root_dir: str = ""
    watch_dir: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CloudflarePagesRoute:
    pattern: str
    zone_name: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        data = {"pattern": self.pattern}
        if self.zone_name:
            data["zone_name"] = self.zone_name
        return data


@dataclass
class CloudflarePagesRedirect:
    from_path: str
    to_path: str
    status_code: int = 301

    def to_dict(self) -> Dict[str, Any]:
        return {"from": self.from_path, "to": self.to_path, "status": self.status_code}


@dataclass
class CloudflarePagesHeader:
    path: str
    headers: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {"path": self.path, "headers": self.headers}


@dataclass
class CloudflarePagesConfig:
    name: str = "iptv"
    compatibility_date: str = "2024-01-01"
    build: CloudflarePagesBuild = field(default_factory=CloudflarePagesBuild)
    routes: List[CloudflarePagesRoute] = field(default_factory=list)
    redirects: List[CloudflarePagesRedirect] = field(default_factory=list)
    headers: List[CloudflarePagesHeader] = field(default_factory=list)
    env_vars: Dict[str, str] = field(default_factory=dict)
    functions_dir: str = "functions"
    static_assets: List[str] = field(default_factory=lambda: ["data/output"])

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "compatibility_date": self.compatibility_date,
            "build": self.build.to_dict(),
            "routes": [r.to_dict() for r in self.routes],
            "redirects": [r.to_dict() for r in self.redirects],
            "headers": [h.to_dict() for h in self.headers],
            "env_vars": self.env_vars,
            "functions_dir": self.functions_dir,
            "static_assets": self.static_assets,
        }


class CloudflarePagesConfigManager:
    DEFAULT_M3U_HEADERS = {
        "Content-Type": "application/vnd.apple.mpegurl",
        "Cache-Control": "public, max-age=3600",
        "Access-Control-Allow-Origin": "*",
    }

    DEFAULT_TXT_HEADERS = {
        "Content-Type": "text/plain; charset=utf-8",
        "Cache-Control": "public, max-age=3600",
        "Access-Control-Allow-Origin": "*",
    }

    def __init__(self, project_name: str = "iptv"):
        self.project_name = project_name

    def create_default_config(self) -> CloudflarePagesConfig:
        config = CloudflarePagesConfig(
            name=self.project_name,
            build=CloudflarePagesBuild(command="python main.py", output_dir="data/output", root_dir=""),
            headers=[
                CloudflarePagesHeader(path="/m3u/*", headers=self.DEFAULT_M3U_HEADERS),
                CloudflarePagesHeader(path="/txt/*", headers=self.DEFAULT_TXT_HEADERS),
                CloudflarePagesHeader(path="/*.m3u", headers=self.DEFAULT_M3U_HEADERS),
                CloudflarePagesHeader(path="/*.txt", headers=self.DEFAULT_TXT_HEADERS),
            ],
            static_assets=["data/output"],
        )

        return config

    def create_iptv_config(
        self,
        output_dir: str = "data/output",
        include_m3u: bool = True,
        include_txt: bool = True,
    ) -> CloudflarePagesConfig:
        config = self.create_default_config()
        config.build.output_dir = output_dir
        config.static_assets = [output_dir]

        headers_list = []

        if include_m3u:
            headers_list.append(CloudflarePagesHeader(path="/*.m3u", headers=self.DEFAULT_M3U_HEADERS))

        if include_txt:
            headers_list.append(CloudflarePagesHeader(path="/*.txt", headers=self.DEFAULT_TXT_HEADERS))

        config.headers = headers_list

        return config

    def add_route(self, config: CloudflarePagesConfig, pattern: str, zone_name: str = None) -> CloudflarePagesConfig:
        config.routes.append(CloudflarePagesRoute(pattern=pattern, zone_name=zone_name))
        return config

    def add_redirect(
        self,
        config: CloudflarePagesConfig,
        from_path: str,
        to_path: str,
        status_code: int = 301,
    ) -> CloudflarePagesConfig:
        config.redirects.append(CloudflarePagesRedirect(from_path=from_path, to_path=to_path, status_code=status_code))
        return config

    def add_header_rule(
        self, config: CloudflarePagesConfig, path: str, headers: Dict[str, str]
    ) -> CloudflarePagesConfig:
        config.headers.append(CloudflarePagesHeader(path=path, headers=headers))
        return config

    def set_env_var(self, config: CloudflarePagesConfig, key: str, value: str) -> CloudflarePagesConfig:
        config.env_vars[key] = value
        return config

    def to_wrangler_toml(self, config: CloudflarePagesConfig) -> str:
        lines = [
            f'name = "{config.name}"',
            f'compatibility_date = "{config.compatibility_date}"',
            "",
            "[build]",
            f'command = "{config.build.command}"',
            f'output_dir = "{config.build.output_dir}"',
        ]

        if config.build.root_dir:
            lines.append(f'root_dir = "{config.build.root_dir}"')

        if config.routes:
            lines.append("")
            lines.append("[[routes]]")
            for route in config.routes:
                lines.append(f'pattern = "{route.pattern}"')
                if route.zone_name:
                    lines.append(f'zone_name = "{route.zone_name}"')

        if config.headers:
            lines.append("")
            lines.append("[[headers]]")
            for header in config.headers:
                lines.append(f'path = "{header.path}"')
                for key, value in header.headers.items():
                    lines.append(f'  "{key}" = "{value}"')

        return "\n".join(lines)

    def to_pages_json(self, config: CloudflarePagesConfig) -> str:
        data = {"cloudflare": {"pages": config.to_dict()}}
        return json.dumps(data, indent=2, ensure_ascii=False)

    def to_yaml(self, config: CloudflarePagesConfig) -> str:
        return yaml.dump(config.to_dict(), default_flow_style=False, allow_unicode=True)

    def save_wrangler_toml(self, config: CloudflarePagesConfig, file_path: str = "wrangler.toml") -> bool:
        try:
            content = self.to_wrangler_toml(config)
            Path(file_path).write_text(content, encoding="utf-8")
            logger.info(f"Saved wrangler.toml to {file_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to save wrangler.toml: {e}")
            return False

    def save_pages_json(self, config: CloudflarePagesConfig, file_path: str = "pages.json") -> bool:
        try:
            content = self.to_pages_json(config)
            Path(file_path).write_text(content, encoding="utf-8")
            logger.info(f"Saved pages.json to {file_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to save pages.json: {e}")
            return False

    def save_yaml(self, config: CloudflarePagesConfig, file_path: str = ".cloudflare.yaml") -> bool:
        try:
            content = self.to_yaml(config)
            Path(file_path).write_text(content, encoding="utf-8")
            logger.info(f"Saved Cloudflare config to {file_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to save YAML config: {e}")
            return False

    def load_from_file(self, file_path: str) -> Optional[CloudflarePagesConfig]:
        path = Path(file_path)

        if not path.exists():
            logger.error(f"Config file not found: {file_path}")
            return None

        try:
            suffix = path.suffix.lower()

            if suffix == ".json":
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                if "cloudflare" in data and "pages" in data["cloudflare"]:
                    data = data["cloudflare"]["pages"]

                return self._dict_to_config(data)

            elif suffix in [".yaml", ".yml"]:
                with open(path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                return self._dict_to_config(data)

            elif suffix == ".toml":
                return self._parse_toml(path)

            else:
                logger.error(f"Unsupported config format: {suffix}")
                return None

        except Exception as e:
            logger.error(f"Failed to load config from {file_path}: {e}")
            return None

    def _dict_to_config(self, data: Dict[str, Any]) -> CloudflarePagesConfig:
        build_data = data.get("build", {})
        build = CloudflarePagesBuild(
            command=build_data.get("command", "python main.py"),
            output_dir=build_data.get("output_dir", "data/output"),
            root_dir=build_data.get("root_dir", ""),
            watch_dir=build_data.get("watch_dir", ""),
        )

        routes = []
        for r in data.get("routes", []):
            routes.append(CloudflarePagesRoute(pattern=r.get("pattern", ""), zone_name=r.get("zone_name")))

        redirects = []
        for r in data.get("redirects", []):
            redirects.append(
                CloudflarePagesRedirect(
                    from_path=r.get("from", ""),
                    to_path=r.get("to", ""),
                    status_code=r.get("status", 301),
                )
            )

        headers = []
        for h in data.get("headers", []):
            headers.append(CloudflarePagesHeader(path=h.get("path", ""), headers=h.get("headers", {})))

        return CloudflarePagesConfig(
            name=data.get("name", self.project_name),
            compatibility_date=data.get("compatibility_date", "2024-01-01"),
            build=build,
            routes=routes,
            redirects=redirects,
            headers=headers,
            env_vars=data.get("env_vars", {}),
            functions_dir=data.get("functions_dir", "functions"),
            static_assets=data.get("static_assets", ["data/output"]),
        )

    def _parse_toml(self, path: Path) -> Optional[CloudflarePagesConfig]:
        try:
            import tomli

            with open(path, "rb") as f:
                data = tomli.load(f)
            return self._dict_to_config(data)
        except ImportError:
            logger.warning("tomli not installed, attempting manual TOML parsing")
            return self._manual_toml_parse(path)

    def _manual_toml_parse(self, path: Path) -> Optional[CloudflarePagesConfig]:
        config = self.create_default_config()

        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()

            import re

            name_match = re.search(r'^name\s*=\s*"([^"]+)"', content, re.MULTILINE)
            if name_match:
                config.name = name_match.group(1)

            compat_match = re.search(r'^compatibility_date\s*=\s*"([^"]+)"', content, re.MULTILINE)
            if compat_match:
                config.compatibility_date = compat_match.group(1)

            command_match = re.search(r'command\s*=\s*"([^"]+)"', content)
            if command_match:
                config.build.command = command_match.group(1)

            output_match = re.search(r'output_dir\s*=\s*"([^"]+)"', content)
            if output_match:
                config.build.output_dir = output_match.group(1)

            return config

        except Exception as e:
            logger.error(f"Failed to parse TOML manually: {e}")
            return None


class CloudflarePagesService:
    def __init__(self, project_name: str = "iptv"):
        self.manager = CloudflarePagesConfigManager(project_name)

    def generate_default_config(self, output_dir: str = None) -> CloudflarePagesConfig:
        if output_dir:
            return self.manager.create_iptv_config(output_dir=output_dir)
        return self.manager.create_default_config()

    def generate_all_configs(self, output_dir: str = "data/output") -> Dict[str, str]:
        config = self.manager.create_iptv_config(output_dir=output_dir)

        configs = {
            "wrangler.toml": self.manager.to_wrangler_toml(config),
            "pages.json": self.manager.to_pages_json(config),
            ".cloudflare.yaml": self.manager.to_yaml(config),
        }

        return configs

    def save_all_configs(self, output_dir: str = "data/output", base_path: str = ".") -> Dict[str, bool]:
        config = self.manager.create_iptv_config(output_dir=output_dir)
        base = Path(base_path)

        results = {
            "wrangler.toml": self.manager.save_wrangler_toml(config, str(base / "wrangler.toml")),
            "pages.json": self.manager.save_pages_json(config, str(base / "pages.json")),
            ".cloudflare.yaml": self.manager.save_yaml(config, str(base / ".cloudflare.yaml")),
        }

        return results

    def load_config(self, file_path: str) -> Optional[CloudflarePagesConfig]:
        return self.manager.load_from_file(file_path)

    def create_headers_file(self, output_dir: str = "data/output", file_path: str = "_headers") -> bool:
        headers_content = """# IPTV Headers Configuration
# M3U files
/*.m3u
  Content-Type: application/vnd.apple.mpegurl
  Cache-Control: public, max-age=3600
  Access-Control-Allow-Origin: *

# TXT files
/*.txt
  Content-Type: text/plain; charset=utf-8
  Cache-Control: public, max-age=3600
  Access-Control-Allow-Origin: *

# M3U directory
/m3u/*
  Content-Type: application/vnd.apple.mpegurl
  Cache-Control: public, max-age=3600
  Access-Control-Allow-Origin: *

# TXT directory
/txt/*
  Content-Type: text/plain; charset=utf-8
  Cache-Control: public, max-age=3600
  Access-Control-Allow-Origin: *
"""

        try:
            Path(file_path).write_text(headers_content, encoding="utf-8")
            logger.info(f"Created _headers file at {file_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to create _headers file: {e}")
            return False

    def create_redirects_file(self, redirects: List[Dict[str, str]] = None, file_path: str = "_redirects") -> bool:
        default_redirects = [
            {"from": "/m3u", "/to": "/m3u/iptv.m3u", "status": "301"},
            {"from": "/txt", "/to": "/txt/iptv.txt", "status": "301"},
        ]

        redirects = redirects or default_redirects

        lines = []
        for r in redirects:
            lines.append(f"{r['from']} {r['to']} {r.get('status', '301')}")

        content = "\n".join(lines) + "\n"

        try:
            Path(file_path).write_text(content, encoding="utf-8")
            logger.info(f"Created _redirects file at {file_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to create _redirects file: {e}")
            return False
