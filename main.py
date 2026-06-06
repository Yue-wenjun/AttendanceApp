import eel
import json
import os
import socket
import threading
import time
import webbrowser
import chinese_calendar
import calendar  # 【新增导入这个官方库】
from datetime import datetime, timedelta

# 数据文件路径
DATA_FILE = "attendance_log.json"

# 默认设置（用于新人员或新字段补全）
default_settings = {
    "start_date": "2026-04-20",
    "payday": 1,
    "daily_wage": 600.0,
    "monthly_salary": 15000.0,
    "mode": "internship",
    "overtime_multiplier": 2.0,
}

DEFAULT_PERSON = "我"


class AttendanceManager:
    """多人考勤数据管理。
    数据结构：
    {
      "current_person": "我",
      "people": {
        "我":   {"settings": {...}, "records": {date: status}},
        "肖荷": {"settings": {...}, "records": {...}}
      }
    }
    自动兼容旧版单人格式 {"settings": ..., "records": ...}。
    """

    def __init__(self):
        self.data = self._load_or_init()
        self._ensure_invariants()
        self._save()

    # -------- 文件加载/迁移 --------
    def _load_or_init(self):
        if not os.path.exists(DATA_FILE):
            return {
                "current_person": DEFAULT_PERSON,
                "people": {
                    DEFAULT_PERSON: {
                        "settings": dict(default_settings),
                        "records": {},
                    }
                },
            }
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)

        # 旧格式迁移：顶层有 settings/records 但没有 people
        if "people" not in raw and ("settings" in raw or "records" in raw):
            return {
                "current_person": DEFAULT_PERSON,
                "people": {
                    DEFAULT_PERSON: {
                        "settings": raw.get("settings", dict(default_settings)),
                        "records": raw.get("records", {}),
                    }
                },
            }
        return raw

    def _ensure_invariants(self):
        """保证结构完整：people 至少有默认人员；每人 settings 字段齐全。"""
        if "people" not in self.data or not isinstance(self.data["people"], dict):
            self.data["people"] = {}
        if not self.data["people"]:
            self.data["people"][DEFAULT_PERSON] = {
                "settings": dict(default_settings),
                "records": {},
            }

        # 当前选中人员；若失效则回退到第一个
        cur = self.data.get("current_person")
        if not cur or cur not in self.data["people"]:
            self.data["current_person"] = next(iter(self.data["people"]))

        # 给每个人补齐 settings 默认字段
        for name, person in self.data["people"].items():
            if not isinstance(person, dict):
                person = {"settings": {}, "records": {}}
                self.data["people"][name] = person
            person.setdefault("settings", {})
            person.setdefault("records", {})
            for k, v in default_settings.items():
                person["settings"].setdefault(k, v)

    def _save(self):
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=4)

    # -------- 当前人员快捷访问 --------
    @property
    def current_person(self):
        return self.data["current_person"]

    @property
    def settings(self):
        return self.data["people"][self.current_person]["settings"]

    @property
    def records(self):
        return self.data["people"][self.current_person]["records"]

    def list_people(self):
        return list(self.data["people"].keys())

    def switch_person(self, name):
        if name not in self.data["people"]:
            return False
        self.data["current_person"] = name
        self._save()
        return True

    def add_person(self, name):
        name = (name or "").strip()
        if not name:
            return False
        if name in self.data["people"]:
            return False
        self.data["people"][name] = {
            "settings": dict(default_settings),
            "records": {},
        }
        self.data["current_person"] = name
        self._save()
        return True

    def delete_person(self, name):
        if name not in self.data["people"]:
            return False
        if len(self.data["people"]) <= 1:
            return False  # 至少保留一人
        del self.data["people"][name]
        if self.data["current_person"] == name:
            self.data["current_person"] = next(iter(self.data["people"]))
        self._save()
        return True

    def save_all(self):
        self._save()


manager = AttendanceManager()

# ================= 暴露给前端 JS 的 Python 函数 =================


@eel.expose
def get_people():
    """返回所有人员名单 + 当前选中人员。"""
    return {
        "people": manager.list_people(),
        "current": manager.current_person,
    }


@eel.expose
def switch_person(name):
    """切换当前人员。"""
    ok = manager.switch_person(name)
    print(f"后端: 切换到 {name} -> {ok}")
    return ok


@eel.expose
def add_person(name):
    """新增人员（默认设置），并自动切换过去。"""
    ok = manager.add_person(name)
    print(f"后端: 新增人员 {name} -> {ok}")
    return ok


@eel.expose
def delete_person(name):
    """删除人员。"""
    ok = manager.delete_person(name)
    print(f"后端: 删除人员 {name} -> {ok}")
    return ok


@eel.expose
def get_initial_data(year, month):
    """获取当前人员的记录与设置。"""
    print(f"后端: 获取数据 {year}-{month} (当前人员: {manager.current_person})")
    return {
        "settings": manager.settings,
        "records": manager.records,  # 所有记录，JS端自己筛选
        "current_person": manager.current_person,
        "people": manager.list_people(),
    }


@eel.expose
def is_holiday_or_workday(date_str):
    """判断某天是否为法定节假日或调休工作日"""
    try:
        date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
        is_holiday = chinese_calendar.is_holiday(date_obj)
        is_workday = chinese_calendar.is_workday(date_obj)

        try:
            on_holiday, name = chinese_calendar.get_holiday_detail(date_obj)
            if on_holiday:
                return {"type": "holiday", "name": name or "节假日"}
        except:
            pass  # 不是法定节假日

        if is_workday:
            return {"type": "workday"}
        else:
            return {"type": "weekend"}  # 普通周末

    except ValueError:
        return {"type": "unknown"}


@eel.expose
def save_record(date_str, status):
    """保存或删除某天的打卡记录（针对当前选中人员）"""
    print(f"后端: 记录 [{manager.current_person}] {date_str} 为 {status}")
    if status == "none":
        if date_str in manager.records:
            del manager.records[date_str]
    else:
        manager.records[date_str] = status
    manager.save_all()
    return True


@eel.expose
def update_settings(wage, payday, mode, monthly_salary, overtime_multiplier):
    """接收前端传来的新设置并保存（针对当前选中人员），包含严格的容错处理"""
    try:
        s = manager.settings
        s["daily_wage"] = float(wage) if str(wage).strip() else 600.0
        s["payday"] = int(payday) if str(payday).strip() else 10
        s["mode"] = mode
        s["monthly_salary"] = (
            float(monthly_salary) if str(monthly_salary).strip() else 15000.0
        )
        s["overtime_multiplier"] = (
            float(overtime_multiplier) if str(overtime_multiplier).strip() else 2.0
        )

        manager.save_all()
        print(
            f"后端: [{manager.current_person}] 设置已更新 -> 模式:{mode}, 日薪:{s['daily_wage']}, 倍率:{s['overtime_multiplier']}"
        )
        return True
    except Exception as e:
        print(f"❌ 后端保存设置报错: {e}")
        return False


@eel.expose
def get_final_stats(year, month):
    """计算当前选中人员的统计与薪资。"""
    status_map = {"work": "上班", "overtime": "加班", "leave": "请假"}

    settings = manager.settings
    records = manager.records

    payday = int(settings.get("payday", 10))
    mode = settings.get("mode", "internship")
    daily_wage = float(settings.get("daily_wage", 600.0))
    monthly_salary = float(settings.get("monthly_salary", 15000.0))
    multiplier = float(settings.get("overtime_multiplier", 2.0))

    if payday == 1:
        cycle_start_date = datetime(year, month, 1).date()
        _, last_day = calendar.monthrange(year, month)
        cycle_end_date = datetime(year, month, last_day).date()
    else:
        prev_month = month - 1 if month > 1 else 12
        prev_year = year if month > 1 else year - 1
        _, last_day_prev = calendar.monthrange(prev_year, prev_month)
        actual_start_day = min(payday, last_day_prev)
        cycle_start_date = datetime(prev_year, prev_month, actual_start_day).date()

        _, last_day_curr = calendar.monthrange(year, month)
        actual_end_day = min(payday - 1, last_day_curr)
        cycle_end_date = datetime(year, month, actual_end_day).date()

    start_date = datetime.strptime(settings["start_date"], "%Y-%m-%d").date()
    end_date = datetime.now().date()
    total_stats = {"上班": 0, "加班": 0, "请假": 0, "应出勤未打卡": 0}
    current = start_date
    while current <= end_date:
        date_key = current.strftime("%Y-%m-%d")
        if date_key in records:
            mapped_status = status_map.get(records[date_key], records[date_key])
            if mapped_status in total_stats:
                total_stats[mapped_status] += 1
        elif chinese_calendar.is_workday(current):
            total_stats["应出勤未打卡"] += 1
        current += timedelta(days=1)

    cycle_stats = {"上班": 0, "加班": 0, "请假": 0}
    curr_iter = cycle_start_date
    while curr_iter <= cycle_end_date:
        date_key = curr_iter.strftime("%Y-%m-%d")
        if date_key in records:
            mapped_status = status_map.get(records[date_key], records[date_key])
            if mapped_status in cycle_stats:
                cycle_stats[mapped_status] += 1
        curr_iter += timedelta(days=1)

    if mode == "internship":
        payable_days = cycle_stats["上班"] + (cycle_stats["加班"] * multiplier)
        salary = payable_days * daily_wage
    else:
        payable_days = "按月固定"
        salary = (
            monthly_salary
            + (cycle_stats["加班"] * multiplier * daily_wage)
            - (cycle_stats["请假"] * daily_wage)
        )
        if salary < 0:
            salary = 0

    return {
        "person": manager.current_person,
        "overall": {
            "start_date": settings["start_date"],
            "end_date": end_date.strftime("%Y-%m-%d"),
            "data": total_stats,
        },
        "salary": {
            "year": year,
            "month": month,
            "mode": mode,
            "wage": daily_wage,
            "monthly_salary": monthly_salary,
            "multiplier": multiplier,
            "payable_days": payable_days,
            "details": cycle_stats,
            "cycle_start": cycle_start_date.strftime("%Y-%m-%d"),
            "cycle_end": cycle_end_date.strftime("%Y-%m-%d"),
            "estimated_salary": salary,
        },
    }


# 初始化 Eel，指定 web 文件夹路径
eel.init("web")

PORT = 8080
URL = f"http://localhost:{PORT}/index.html"


def _open_browser_when_ready():
    """等服务器真正起来再开浏览器。
    eel 默认是“先开浏览器、再起服务器”，本机没装 Chrome 时会退回到默认浏览器，
    结果浏览器抢在服务器之前打开 → 显示“无法连接”。这里改成轮询端口，
    确认服务起来后再用系统默认浏览器打开，避免打不开。
    """
    for _ in range(60):  # 最多等 ~30 秒
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", PORT)) == 0:
                break
        time.sleep(0.5)
    webbrowser.open(URL)


print("打卡程序已启动，正在打开浏览器界面...")
print(f"如果没自动弹出来，手动在浏览器打开这个地址即可： {URL}")
print("（按 Ctrl+C 退出程序）")

# 后台线程负责“等服务器起来再开浏览器”；mode=None 让 eel 自己不去找 Chrome
threading.Thread(target=_open_browser_when_ready, daemon=True).start()
eel.start("index.html", size=(1100, 750), port=PORT, mode=None)