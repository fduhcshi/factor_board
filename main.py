"""命令行入口：解析参数、加载配置、执行因子计算流程。"""

from __future__ import annotations

import argparse
import logging
import sys

from factor_dashboard.pipeline import FactorPipeline
from factor_dashboard.settings import ConfigError, load_config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="聚宽因子库公式的 AKShare 复现")
    parser.add_argument(
        "--config",
        default=None,
        help="配置文件路径；省略时读取 configs/default.yaml",
    )
    parser.add_argument(
        "--verbose", action="store_true", help="输出调试日志"
    )
    return parser.parse_args()


def configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def main() -> int:
    args = parse_args()
    configure_logging(args.verbose)
    try:
        config = load_config(args.config)
    except ConfigError as exc:
        logging.error("配置错误：%s", exc)
        return 2

    try:
        run_dir = FactorPipeline(config).run()
    except Exception as exc:  # 入口处兜底，保证返回非零退出码
        logging.exception("运行失败：%s", exc)
        return 1

    logging.info("完成，结果位于 %s", run_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
