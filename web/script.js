// script.js - 可视化交互逻辑
let currentDate = new Date();
let appSettings = {};
let attendanceRecords = {};

// 状态循环数组
const STATUS_CYCLE = ["none", "work", "overtime", "leave"];
const STATUS_LABELS = { "none": "", "work": "上班", "overtime": "加班", "leave": "请假" };

window.onload = async function() {
    updateMonthDisplay();
    await loadInitialData();
    await renderCalendar();
    await refreshStats();
    
    document.getElementById('prevMonth').addEventListener('click', () => changeMonth(-1));
    document.getElementById('nextMonth').addEventListener('click', () => changeMonth(1));
    document.getElementById('refreshStats').addEventListener('click', refreshStats);
    document.getElementById('saveSettingsBtn').addEventListener('click', saveSettings);
    document.getElementById('modeSelect').addEventListener('change', toggleModeUI);

    document.querySelectorAll('.settings-card input, .settings-card select').forEach(el => {
        el.addEventListener('change', saveSettings);
        el.addEventListener('keyup', (e) => {
            if(e.key === 'Enter') saveSettings();
        });
    });
};

// --- 数据加载 ---

async function loadInitialData() {
    const year = currentDate.getFullYear();
    const month = currentDate.getMonth() + 1;
    const data = await eel.get_initial_data(year, month)();
    
    appSettings = data.settings;
    attendanceRecords = data.records;
    
    document.getElementById('modeSelect').value = appSettings.mode || 'internship';
    document.getElementById('wageInput').value = appSettings.daily_wage || 600;
    document.getElementById('monthlyInput').value = appSettings.monthly_salary || 15000;
    document.getElementById('multiplierInput').value = appSettings.overtime_multiplier || 2.0;
    document.getElementById('paydayInput').value = appSettings.payday || 10;
    
    toggleModeUI();
}

// 保存设置传参
async function saveSettings() {
    const mode = document.getElementById('modeSelect').value;
    const wage = document.getElementById('wageInput').value;
    const monthly = document.getElementById('monthlyInput').value;
    const multiplier = document.getElementById('multiplierInput').value;
    const payday = document.getElementById('paydayInput').value;
    
    await eel.update_settings(wage, payday, mode, monthly, multiplier)(); 
    await refreshStats(); 
    
    const btn = document.getElementById('saveSettingsBtn');
    btn.innerText = "✅ 已自动同步";
    btn.style.backgroundColor = "#22c55e"; 
    setTimeout(() => {
        btn.innerText = "手动保存";
        btn.style.backgroundColor = ""; 
    }, 1500);
}

// --- 日历渲染 ---

async function renderCalendar() {
    const grid = document.getElementById('calendarGrid');
    grid.innerHTML = ''; // 清空格子

    const year = currentDate.getFullYear();
    const month = currentDate.getMonth();

    const firstDay = new Date(year, month, 1);
    const lastDay = new Date(year, month + 1, 0);
    
    // 确定星期几开始 (0=日, 6=六)
    let startDayOfWeek = firstDay.getDay(); 
    const totalDays = lastDay.getDate();
    
    // 处理上个月的格子
    const prevMonthLastDay = new Date(year, month, 0).getDate();
    for (let i = startDayOfWeek - 1; i >= 0; i--) {
        const cell = document.createElement('div');
        cell.className = 'day-cell other-month';
        cell.innerHTML = `<span class="day-number">${prevMonthLastDay - i}</span>`;
        grid.appendChild(cell);
    }

    // 绘制本月的格子
    for (let i = 1; i <= totalDays; i++) {
        const cell = document.createElement('div');
        cell.className = 'day-cell';
        const dateStr = `${year}-${String(month + 1).padStart(2, '0')}-${String(i).padStart(2, '0')}`;
        cell.id = `cell_${dateStr}`;
        
        // 1. 添加日期数字
        cell.innerHTML = `<span class="day-number">${i}</span>`;
        // 2. 添加状态文字提示标签
        const labelSpan = document.createElement('span');
        labelSpan.className = 'day-label';
        cell.appendChild(labelSpan);

        // 3. 并行调用 Python，判断法定节假日（优化体验）
        checkAndApplyHolidayStyle(dateStr, cell);

        // 4. 应用已有的历史记录样式（涂色）
        if (attendanceRecords[dateStr]) {
            const status = attendanceRecords[dateStr];
            applyStatusStyle(cell, status);
        }

        // 5. 绑定点击事件 - 可视化涂色操作的关键
        cell.addEventListener('click', () => handleCellClick(dateStr, cell));

        grid.appendChild(cell);
    }
    
    // 处理下个月的格子，确保网格整齐 (总是 6 行)
    const currentCellsCount = startDayOfWeek + totalDays;
    if (currentCellsCount < 42) {
        for (let i = 1; i <= (42 - currentCellsCount); i++) {
            const cell = document.createElement('div');
            cell.className = 'day-cell other-month';
            cell.innerHTML = `<span class="day-number">${i}</span>`;
            grid.appendChild(cell);
        }
    }
}

// 调用 Python 异步检查节假日
async function checkAndApplyHolidayStyle(dateStr, cellElement) {
    // eel.is_holiday_or_workday 是 Python 的暴露函数
    const result = await eel.is_holiday_or_workday(dateStr)();
    if (result.type === 'holiday') {
        cellElement.classList.add('holiday');
        if (result.name) cellElement.title = result.name; // 鼠标悬停显示名称
    } else if (result.type === 'weekend') {
        cellElement.classList.add('holiday');
        cellElement.title = "周末休息日";
    }
}

// --- 交互操作 ---

async function handleCellClick(dateStr, cellElement) {
    // 1. 获取当前状态
    let currentStatus = "none";
    if (attendanceRecords[dateStr]) {
        currentStatus = attendanceRecords[dateStr];
    }
    
    // 2. 找到状态在循环数组中的索引
    let currentIndex = STATUS_CYCLE.indexOf(currentStatus);
    // 如果日期已被 chinese_calendar 判断为休息日，我们允许自由打卡，不做限制
    
    // 3. 计算下一个状态
    let nextIndex = (currentIndex + 1) % STATUS_CYCLE.length;
    let nextStatus = STATUS_CYCLE[nextIndex];
    
    // 4. 应用到界面 (涂色/文字)
    clearStatusStyles(cellElement);
    if (nextStatus !== "none") {
        applyStatusStyle(cellElement, nextStatus);
        attendanceRecords[dateStr] = nextStatus; // 同步内存数据
    } else {
        delete attendanceRecords[dateStr]; // 从内存中移除
    }
    
    // 5. 将结果发送到 Python 后端保存 (log数据持久化)
    await eel.save_record(dateStr, nextStatus)();
    
    // 6. 操作完成后自动刷新右侧的薪资预估，体验更好
    await refreshStats();
}

// 辅助：设置格子的状态样式
function applyStatusStyle(cellElement, status) {
    if (status === "work") {
        cellElement.classList.add('status-work');
    } else if (status === "overtime") {
        cellElement.classList.add('status-overtime');
    } else if (status === "leave") {
        cellElement.classList.add('status-leave');
    }
    // 设置文字
    cellElement.querySelector('.day-label').innerText = STATUS_LABELS[status];
}

// 辅助：清空所有打卡相关的样式
function clearStatusStyles(cellElement) {
    cellElement.classList.remove('status-work', 'status-overtime', 'status-leave');
    cellElement.querySelector('.day-label').innerText = '';
}

// --- 统计与薪资 ---

async function refreshStats() {
    const year = currentDate.getFullYear();
    const month = currentDate.getMonth() + 1;
    
    // 调用 Python 计算所有统计和薪资
    const stats = await eel.get_final_stats(year, month)();
    
    updateSalaryCard(stats.salary);
    updateOverallCard(stats.overall);
}

function updateSalaryCard(salaryData) {
    const content = document.getElementById('salaryContent');
    const est = salaryData.estimated_salary.toFixed(2).replace(/\d(?=(\d{3})+\.)/g, '$&,'); 
    
    let html = `
        <div class="data-p"><span class="data-label">计薪周期：</span><span class="data-value" style="font-size: 0.85rem; color: #6366f1;">${salaryData.cycle_start} 至 ${salaryData.cycle_end}</span></div>
        <hr style="border: 1px dashed #eee; margin: 8px 0;">
    `;
    
    if (salaryData.mode === 'formal') {
        html += `
            <div class="data-p"><span class="data-label">计薪模式：</span><span class="data-value" style="color:#0ea5e9;">正式 (按月)</span></div>
            <div class="data-p"><span class="data-label">出勤明细：</span><span class="data-value">加班 <b>${salaryData.details['加班']}</b> 天 | 请假 <b style="color:#ef4444;">${salaryData.details['请假']}</b> 天</span></div>
            <div class="data-p"><span class="data-label">固定底薪：</span><span class="data-value">¥${salaryData.monthly_salary}</span></div>
            <div class="data-p"><span class="data-label" style="font-size:0.8rem; color:#888;">算法: 底薪 + (加班×${salaryData.multiplier}) - 请假</span></div>
        `;
    } else {
         html += `
            <div class="data-p"><span class="data-label">计薪模式：</span><span class="data-value" style="color:#22c55e;">实习 (按天)</span></div>
            <div class="data-p"><span class="data-label">出勤明细：</span><span class="data-value">上班 <b>${salaryData.details['上班']}</b> 天 | 加班 <b style="color:#22c55e;">${salaryData.details['加班']}</b> 天</span></div>
            <div class="data-p"><span class="data-label">请假天数：</span><span class="data-value" style="color:#ef4444;">${salaryData.details['请假']} 天</span></div>
            <div class="data-p"><span class="data-label">折算计薪天数：</span><span class="data-value" title="上班 + 加班×倍率">${salaryData.payable_days} 天 <span style="font-size:0.75rem; color:#888;">(已×${salaryData.multiplier}倍)</span></span></div>
            <div class="data-p"><span class="data-label">实习日薪：</span><span class="data-value">¥${salaryData.wage}/天</span></div>
        `;
    }

    html += `
        <hr style="border: 1px dashed #eee; margin: 8px 0;">
        <div class="data-p"><span class="data-label" style="font-size: 1.1rem;">💰 预估薪资：</span><span class="data-value important">¥${est}</span></div>
    `;
    
    content.innerHTML = html;
}

function updateOverallCard(overallData) {
    const content = document.getElementById('statsContent');
    const d = overallData.data;
    
    content.innerHTML = `
        <div class="data-p"><span class="data-label">入职日期：</span><span class="data-value">${overallData.start_date}</span></div>
        <div class="data-p"><span class="data-label">统计至：</span><span class="data-value">${overallData.end_date}</span></div>
        <hr style="border: 1px dashed #eee; margin: 8px 0;">
        <div class="data-p"><span class="data-label">上班累计：</span><span class="data-value">${d['上班']} 天</span></div>
        <div class="data-p"><span class="data-label">加班累计：</span><span class="data-value">${d['加班']} 天</span></div>
        <div class="data-p"><span class="data-label">请假累计：</span><span class="data-value bad">${d['请假']} 天</span></div>
    `;
}

// --- 模式 UI 切换 ---

function toggleModeUI() {
    const mode = document.getElementById('modeSelect').value;
    const isInternship = mode === 'internship';
    document.getElementById('dailyWageGroup').style.display = isInternship ? 'flex' : 'none';
    document.getElementById('monthlyWageGroup').style.display = isInternship ? 'none' : 'flex';
    const label = document.getElementById('dailyWageLabel');
    if (label) {
        label.textContent = isInternship ? '💰 实习日薪 (元): ' : '💰 日薪 (元, 加班计算用): ';
    }
}

// --- 月份切换 ---

function changeMonth(delta) {
    currentDate.setMonth(currentDate.getMonth() + delta);
    updateMonthDisplay();
    loadInitialData().then(() => {
        renderCalendar();
        refreshStats(); // 切换月份时也更新右侧薪资
    });
}

function updateMonthDisplay() {
    const year = currentDate.getFullYear();
    const month = currentDate.getMonth() + 1;
    document.getElementById('monthYearDisplay').innerText = `${year}年${month}月`;
}