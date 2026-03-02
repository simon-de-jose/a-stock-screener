"""FastAPI 主程序 + API"""

import threading
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from db import init_db, get_stock_by_name, get_concepts_for_stock, search_match, get_conn

init_db()

app = FastAPI(title="A股选股平台")
templates = Jinja2Templates(directory="templates")


# ── 数据模型 ──────────────────────────────────────────

class MatchRequest(BaseModel):
    chars: list[str] = []
    char_mode: str = "or"  # "or" | "and"
    concept_ids: list[int] = []
    markets: list[str] = []


# ── 页面 ──────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


# ── API ───────────────────────────────────────────────

@app.get("/api/search")
async def api_search(name: str = ""):
    """输入股票名称 → 拆字 + 返回概念标签"""
    name = name.strip()
    if not name:
        return {"error": "请输入股票名称", "chars": [], "concepts": [], "stock": None}

    stock = get_stock_by_name(name)
    if not stock:
        return {"error": f"未找到 {name}，请先刷新数据", "chars": [], "concepts": [], "stock": None}

    chars = list(set(name))  # 拆字去重
    concepts = []
    concept_rows = []
    conn = get_conn()
    rows = conn.execute("""
        SELECT c.id, c.name FROM concepts c
        JOIN stock_concepts sc ON sc.concept_id = c.id
        WHERE sc.stock_code = ?
    """, (stock["code"],)).fetchall()
    conn.close()
    for r in rows:
        concept_rows.append({"id": r["id"], "name": r["name"]})

    return {
        "error": None,
        "stock": stock,
        "chars": chars,
        "concepts": concept_rows,
    }


@app.post("/api/match")
async def api_match(req: MatchRequest):
    """勾选条件 → 返回匹配股票"""
    results = search_match(
        chars=req.chars,
        concept_ids=req.concept_ids,
        markets=req.markets,
        char_mode=req.char_mode,
    )
    return {"count": len(results), "results": results}


# 刷新进度追踪
refresh_status = {"running": False, "step": "", "progress": 0, "total": 0, "done": False, "error": None}


@app.get("/api/status")
async def api_status():
    """检查数据库状态"""
    conn = get_conn()
    stock_count = conn.execute("SELECT count(*) FROM stocks").fetchone()[0]
    concept_count = conn.execute("SELECT count(*) FROM concepts").fetchone()[0]
    conn.close()
    return {"stock_count": stock_count, "concept_count": concept_count, "empty": stock_count == 0}


@app.get("/api/refresh/progress")
async def api_refresh_progress():
    """获取刷新进度"""
    return refresh_status


@app.post("/api/refresh")
async def api_refresh():
    """手动刷新数据（后台线程）"""
    if refresh_status["running"]:
        return {"message": "刷新已在进行中"}

    from data import fetch_all_with_progress

    def run():
        refresh_status["running"] = True
        refresh_status["done"] = False
        refresh_status["error"] = None
        try:
            fetch_all_with_progress(refresh_status)
        except Exception as e:
            refresh_status["error"] = str(e)
        refresh_status["running"] = False
        refresh_status["done"] = True

    t = threading.Thread(target=run, daemon=True)
    t.start()
    return {"message": "开始刷新"}


# ── 启动 ──────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
