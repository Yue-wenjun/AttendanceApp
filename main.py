import eel
import json
import os
import chinese_calendar
import calendar  # 【新增导入这个官方库】
from datetime import datetime, timedelta

# 数据文件路径
DATA_FILE = "attendance_log.json"

# 初始化数据
default_settings = {
    "start_date": "2026-04-20",
    "payday": 20,
    "daily_wage": 600.0,
    "monthly_salary": 50000.0,
    "mode": "internship",
    "overtime_multiplier": 2.0,  # 🚀 新增：默认加班 2 倍薪资
}


class AttendanceManager:
    def __init__(self):
        self.ensure_data_file()
        self.settings = self.load_settings()
        self.records = self.load_records()

    def ensure_data_file(self):
        if not os.path.exists(DATA_FILE):
            with open(DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(
                    {"settings": default_settings, "records": {}},
                    f,
                    ensure_ascii=False,
                    indent=4,
                )

    def load_settings(self):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        settings = data.get("settings", {})
        updated = False
        for key, value in default_settings.items():
            if key not in settings:
                settings[key] = value
                updated = True

        if updated:
            with open(DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(
                    {"settings": settings, "records": data.get("records", {})},
                    f,
                    ensure_ascii=False,
                    indent=4,
                )

        return settings

    def load_records(self):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f).get("records", {})

    def save_all(self):
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(
                {"settings": self.settings, "records": self.records},
                f,
                ensure_ascii=False,
                indent=4,
            )


manager = AttendanceManager()

# ================= 暴露给前端 JS 的 Python 函数 =================


@eel.expose
def get_initial_data(year, month):
    """获取指定月份的记录设置"""
    print(f"后端: 获取数据 {year}-{month}")
    return {
        "settings": manager.settings,
        "records": manager.records,  # 所有的记录，JS端自己筛选
    }


@eel.expose
def is_holiday_or_workday(date_str):
    """判断某天是否为法定节假日或调休工作日"""
    try:
        date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
        is_holiday = chinese_calendar.is_holiday(date_obj)
        is_workday = chinese_calendar.is_workday(date_obj)
        # chinese_calendar 库判断周末也是 holiday
        # 如果是法定工作日（含调休周六日），显示为正常
        # 如果是周末（非调休），显示为周末
        # 如果是法定节假日，显示为节假日

        # 简单处理：如果是工作日返回"work", 否则返回"holiday" (含周末和节假日)
        # 我们可以提供更细致的分类
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
    """保存或删除某天的打卡记录"""
    print(f"后端: 记录 {date_str} 为 {status}")
    if status == "none":
        if date_str in manager.records:
            del manager.records[date_str]
    else:
        manager.records[date_str] = status
    manager.save_all()
    return True


@eel.expose
def update_settings(wage, payday, mode, monthly_salary, overtime_multiplier):
    """接收前端传来的新设置并保存，包含严格的容错处理"""
    try:
        manager.settings["daily_wage"] = float(wage) if str(wage).strip() else 600.0
        manager.settings["payday"] = int(payday) if str(payday).strip() else 10
        manager.settings["mode"] = mode
        manager.settings["monthly_salary"] = (
            float(monthly_salary) if str(monthly_salary).strip() else 15000.0
        )
        manager.settings["overtime_multiplier"] = (
            float(overtime_multiplier) if str(overtime_multiplier).strip() else 2.0
        )

        manager.save_all()
        print(
            f"后端: 设置已更新 -> 模式:{mode}, 日薪:{manager.settings['daily_wage']}, 倍率:{manager.settings['overtime_multiplier']}"
        )
        return True
    except Exception as e:
        print(f"❌ 后端保存设置报错: {e}")
        return False


@eel.expose
def get_final_stats(year, month):
    status_map = {"work": "上班", "overtime": "加班", "leave": "请假"}

    payday = int(manager.settings.get("payday", 10))
    mode = manager.settings.get("mode", "internship")
    daily_wage = float(manager.settings.get("daily_wage", 600.0))
    monthly_salary = float(manager.settings.get("monthly_salary", 15000.0))
    multiplier = float(manager.settings.get("overtime_multiplier", 2.0))

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

    start_date = datetime.strptime(manager.settings["start_date"], "%Y-%m-%d").date()
    end_date = datetime.now().date()
    total_stats = {"上班": 0, "加班": 0, "请假": 0, "应出勤未打卡": 0}
    current = start_date
    while current <= end_date:
        date_key = current.strftime("%Y-%m-%d")
        if date_key in manager.records:
            mapped_status = status_map.get(
                manager.records[date_key], manager.records[date_key]
            )
            if mapped_status in total_stats:
                total_stats[mapped_status] += 1
        elif chinese_calendar.is_workday(current):
            total_stats["应出勤未打卡"] += 1
        current += timedelta(days=1)

    cycle_stats = {"上班": 0, "加班": 0, "请假": 0}
    curr_iter = cycle_start_date
    while curr_iter <= cycle_end_date:
        date_key = curr_iter.strftime("%Y-%m-%d")
        if date_key in manager.records:
            mapped_status = status_map.get(
                manager.records[date_key], manager.records[date_key]
            )
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
        "overall": {
            "start_date": manager.settings["start_date"],
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

print("打卡程序已运行，界面正在打开...")
# 启动程序，可以指定浏览器（推荐 chrome），指定端口（防止冲突）
try:
    eel.start("index.html", size=(1100, 750), port=8080)
except EnvironmentError:
    # 如果没找到默认浏览器
    eel.start("index.html", size=(1100, 750), port=8080, mode="default")
