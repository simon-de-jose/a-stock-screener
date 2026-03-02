"""AKShare 数据采集 + SQLite 写入"""

import logging
import time
import akshare as ak
from db import init_db, upsert_stocks, upsert_concept, batch_link_stock_concepts, mark_limit_up, code_to_market

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)


def fetch_all_stocks():
    """拉取全部A股列表 + 实时行情"""
    log.info("开始拉取A股实时行情...")
    try:
        df = ak.stock_zh_a_spot_em()
    except Exception as e:
        log.error(f"拉取行情失败: {e}")
        return

    log.info(f"获取到 {len(df)} 只股票")

    rows = []
    for _, r in df.iterrows():
        code = str(r["代码"]).zfill(6)
        name = str(r["名称"])
        market = code_to_market(code)
        try:
            price = float(r.get("最新价") or 0)
        except (ValueError, TypeError):
            price = 0
        try:
            cap = float(r.get("流通市值") or 0)
        except (ValueError, TypeError):
            cap = 0
        rows.append(dict(code=code, name=name, market=market, price=price, market_cap=cap))

    upsert_stocks(rows)
    log.info(f"写入 {len(rows)} 只股票 ✓")


def fetch_concepts():
    """拉取概念板块列表 + 每个概念的成分股"""
    log.info("开始拉取概念板块列表...")
    try:
        board_df = ak.stock_board_concept_name_em()
    except Exception as e:
        log.error(f"拉取概念板块列表失败: {e}")
        return

    total = len(board_df)
    log.info(f"共 {total} 个概念板块，逐个拉取成分股...")

    for idx, row in board_df.iterrows():
        concept_name = str(row["板块名称"])
        concept_id = upsert_concept(concept_name)

        try:
            cons_df = ak.stock_board_concept_cons_em(symbol=concept_name)
        except Exception as e:
            log.warning(f"  [{idx+1}/{total}] {concept_name} 成分股拉取失败: {e}")
            time.sleep(0.3)
            continue

        pairs = []
        for _, cr in cons_df.iterrows():
            stock_code = str(cr["代码"]).zfill(6)
            pairs.append((stock_code, concept_id))

        if pairs:
            batch_link_stock_concepts(pairs)

        log.info(f"  [{idx+1}/{total}] {concept_name}: {len(pairs)} 只成分股")
        time.sleep(0.2)  # 避免请求过快

    log.info("概念板块拉取完成 ✓")


def fetch_limit_up():
    """拉取今日涨停股"""
    log.info("开始拉取涨停股...")
    try:
        df = ak.stock_zt_pool_em(date=time.strftime("%Y%m%d"))
        codes = set(str(r["代码"]).zfill(6) for _, r in df.iterrows())
        mark_limit_up(codes)
        log.info(f"涨停股 {len(codes)} 只 ✓")
    except Exception as e:
        log.warning(f"拉取涨停股失败（非交易日可能为空）: {e}")
        mark_limit_up(set())


def fetch_all():
    """全量拉取"""
    init_db()
    fetch_all_stocks()
    fetch_concepts()
    fetch_limit_up()
    log.info("=== 全部数据拉取完成 ===")


def fetch_all_with_progress(status):
    """带进度回调的全量拉取"""
    init_db()
    errors = []

    # Step 1: 股票行情
    status["step"] = "拉取股票行情..."
    status["progress"] = 0
    status["total"] = 3
    try:
        df = ak.stock_zh_a_spot_em()
        rows = []
        for _, r in df.iterrows():
            code = str(r["代码"]).zfill(6)
            name = str(r["名称"])
            market = code_to_market(code)
            try:
                price = float(r.get("最新价") or 0)
            except (ValueError, TypeError):
                price = 0
            try:
                cap = float(r.get("流通市值") or 0)
            except (ValueError, TypeError):
                cap = 0
            rows.append(dict(code=code, name=name, market=market, price=price, market_cap=cap))
        upsert_stocks(rows)
        log.info(f"写入 {len(rows)} 只股票 ✓")
        status["progress"] = 1
    except Exception as e:
        err = f"拉取行情失败: {e}"
        log.error(err)
        errors.append(err)
        status["progress"] = 1

    # Step 2: 概念板块
    status["step"] = "拉取概念板块列表..."
    try:
        board_df = ak.stock_board_concept_name_em()
        total = len(board_df)
        status["total"] = total
        failed_concepts = 0

        for idx, row in board_df.iterrows():
            concept_name = str(row["板块名称"])
            status["step"] = f"拉取概念 ({idx+1}/{total}): {concept_name}"
            status["progress"] = idx + 1

            concept_id = upsert_concept(concept_name)
            try:
                cons_df = ak.stock_board_concept_cons_em(symbol=concept_name)
                pairs = [(str(cr["代码"]).zfill(6), concept_id) for _, cr in cons_df.iterrows()]
                if pairs:
                    batch_link_stock_concepts(pairs)
            except Exception:
                failed_concepts += 1
                time.sleep(0.3)
                continue
            time.sleep(0.2)

        if failed_concepts > 0:
            errors.append(f"{failed_concepts}/{total} 个概念拉取失败")
        status["progress"] = total
    except Exception as e:
        err = f"概念板块列表拉取失败: {e}"
        log.error(err)
        errors.append(err)

    # Step 3: 涨停
    status["step"] = "拉取涨停数据..."
    try:
        fetch_limit_up()
    except Exception as e:
        errors.append(f"涨停数据失败: {e}")

    # 验证结果
    from db import get_conn
    conn = get_conn()
    stock_count = conn.execute("SELECT count(*) FROM stocks").fetchone()[0]
    concept_count = conn.execute("SELECT count(*) FROM concepts").fetchone()[0]
    conn.close()

    if stock_count == 0:
        status["step"] = "失败：未拉取到任何数据"
        status["error"] = "数据拉取失败（可能是网络问题或IP被限制）。错误: " + "; ".join(errors) if errors else "未知错误"
    elif errors:
        status["step"] = f"部分完成：{stock_count}只股票，{concept_count}个概念（有{len(errors)}个错误）"
        status["error"] = "; ".join(errors)
    else:
        status["step"] = f"完成：{stock_count}只股票，{concept_count}个概念"


if __name__ == "__main__":
    fetch_all()
