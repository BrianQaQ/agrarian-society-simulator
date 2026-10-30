"""Observer interface for the bottom-up agrarian simulation."""

from __future__ import annotations

import argparse
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from simulation import AgrarianSimulation, Institution, Strategy


BG, PANEL, PANEL2 = "#131719", "#202628", "#293134"
TEXT, MUTED = "#ece6d7", "#9ba4a2"
GOLD, RED, GREEN, BLUE, CYAN = "#d8b76c", "#df7064", "#78af79", "#739bc5", "#6ebbb2"


class ObserverApp(tk.Tk):
    def __init__(self, seed: int = 7):
        super().__init__()
        self.title("土地、家族与周期 · 底层社会模拟")
        self.geometry("1460x900")
        self.minsize(1180, 740)
        self.configure(bg=BG)
        self.seed = seed
        self.running = False
        self.speed_ms = 280
        self.mode_var = tk.StringVar(value="fixed")
        self.inheritance_var = tk.StringVar(value="均分继承")
        self.values: dict[str, tk.DoubleVar] = {}
        self.kpis: dict[str, tk.StringVar] = {}
        self._styles()
        self._build()
        self._new_simulation()
        self.bind("<space>", lambda _e: self.toggle())
        self.bind("<Right>", lambda _e: self.advance(1))

    def _styles(self) -> None:
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure("TFrame", background=BG)
        s.configure("Panel.TFrame", background=PANEL)
        s.configure("TLabel", background=BG, foreground=TEXT, font=("PingFang SC", 10))
        s.configure("Panel.TLabel", background=PANEL, foreground=TEXT, font=("PingFang SC", 10))
        s.configure("Muted.TLabel", background=PANEL, foreground=MUTED, font=("PingFang SC", 9))
        s.configure("Title.TLabel", background=BG, foreground=TEXT, font=("PingFang SC", 20, "bold"))
        s.configure("Kpi.TLabel", background=PANEL, foreground=GOLD, font=("Menlo", 16, "bold"))
        s.configure("TButton", background=PANEL2, foreground=TEXT, padding=(11, 7))
        s.configure("Accent.TButton", background="#78633c", foreground="#fff8e6")
        s.configure("TRadiobutton", background=PANEL, foreground=TEXT)
        s.configure("TCombobox", fieldbackground=PANEL2, background=PANEL2, foreground=TEXT)
        s.configure("Horizontal.TScale", background=PANEL, troughcolor="#101415")

    def _build(self) -> None:
        head = ttk.Frame(self)
        head.pack(fill="x", padx=18, pady=(14, 8))
        ttk.Label(head, text="土地、家族与周期", style="Title.TLabel").pack(side="left")
        ttk.Label(head, text="　观察者模式：从生存与繁衍推出宏观结构", foreground=MUTED).pack(side="left", pady=(7, 0))
        self.year_label = ttk.Label(head, text="", foreground=GOLD)
        self.year_label.pack(side="right", pady=(7, 0))

        cards = ttk.Frame(self)
        cards.pack(fill="x", padx=18, pady=(0, 8))
        for i, (key, title) in enumerate((("population", "人口"), ("households", "家户"),
                ("gini", "土地基尼"), ("top", "前10%占地"), ("landless", "无地人口"),
                ("fiscal", "财政充足率"), ("cycles", "改朝次数"))):
            f = ttk.Frame(cards, style="Panel.TFrame", padding=(12, 8))
            f.grid(row=0, column=i, sticky="nsew", padx=(0, 6))
            cards.columnconfigure(i, weight=1)
            ttk.Label(f, text=title, style="Muted.TLabel").pack(anchor="w")
            self.kpis[key] = tk.StringVar(value="—")
            ttk.Label(f, textvariable=self.kpis[key], style="Kpi.TLabel").pack(anchor="w", pady=(2, 0))

        body = ttk.Frame(self)
        body.pack(fill="both", expand=True, padx=18)
        body.columnconfigure(0, minsize=300)
        body.columnconfigure(1, weight=3)
        body.columnconfigure(2, weight=2)
        body.rowconfigure(0, weight=1)
        self._controls(body)
        self._charts(body)
        self._strategy_panel(body)

        foot = ttk.Frame(self, style="Panel.TFrame", padding=(12, 8))
        foot.pack(fill="x", padx=18, pady=(8, 14))
        ttk.Label(foot, text="演化事件", style="Panel.TLabel", font=("PingFang SC", 10, "bold")).pack(side="left")
        self.event_label = ttk.Label(foot, text="初始化", style="Muted.TLabel", wraplength=1000)
        self.event_label.pack(side="left", padx=(14, 0))
        ttk.Label(foot, text="年景随机 · 无剧本事件 · 土地守恒", style="Muted.TLabel").pack(side="right")

    def _controls(self, parent: ttk.Frame) -> None:
        panel = ttk.Frame(parent, style="Panel.TFrame", padding=14)
        panel.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        ttk.Label(panel, text="实验设置", style="Panel.TLabel", font=("PingFang SC", 14, "bold")).pack(anchor="w")
        ttk.Label(panel, text="更改模式或参数后点击“按当前设置重置”。", style="Muted.TLabel").pack(anchor="w", pady=(2, 8))
        mode = ttk.Frame(panel, style="Panel.TFrame")
        mode.pack(fill="x", pady=(0, 6))
        ttk.Radiobutton(mode, text="固定规则", variable=self.mode_var, value="fixed", command=self._mode_help).pack(side="left")
        ttk.Radiobutton(mode, text="策略演化", variable=self.mode_var, value="evolution", command=self._mode_help).pack(side="left", padx=(12, 0))
        self.mode_help = ttk.Label(panel, text="", style="Muted.TLabel", wraplength=270)
        self.mode_help.pack(anchor="w", pady=(0, 7))
        self._mode_help()

        inherit_row = ttk.Frame(panel, style="Panel.TFrame")
        inherit_row.pack(fill="x", pady=3)
        ttk.Label(inherit_row, text="固定继承制", style="Panel.TLabel").pack(side="left")
        ttk.Combobox(inherit_row, textvariable=self.inheritance_var, state="readonly", width=10,
                     values=("均分继承", "长子继承")).pack(side="right")

        specs = (
            ("harvest", "年景波动（变异系数）", .00, .50, .20),
            ("interest", "借贷年利率", .10, 1.00, .40),
            ("burden", "开国财政需求/产出", .02, .20, .08),
            ("growth", "财政需求年增长", .000, .020, .007),
            ("evasion", "大户隐田速度/年", .000, .050, .010),
            ("revolt", "国家可镇压的动员比例", .05, .50, .20),
            ("seizure", "战乱夺佃率/年", .00, .50, .15),
            ("subsistence", "人均生存消耗（石）", 3.0, 6.0, 4.0),
            ("fertility", "固定生育率", .02, .06, .04),
            ("reserve", "固定存粮目标/年", .00, 2.50, .50),
            ("acquisition", "固定放贷倾向", .00, 1.00, .60),
            ("mutation", "演化模式变异率", .00, .25, .06),
        )
        for key, title, lo, hi, default in specs:
            row = ttk.Frame(panel, style="Panel.TFrame")
            row.pack(fill="x", pady=2)
            top = ttk.Frame(row, style="Panel.TFrame")
            top.pack(fill="x")
            ttk.Label(top, text=title, style="Panel.TLabel").pack(side="left")
            value_label = ttk.Label(top, text="", style="Muted.TLabel")
            value_label.pack(side="right")
            var = tk.DoubleVar(value=default)
            self.values[key] = var
            ttk.Scale(row, from_=lo, to=hi, variable=var,
                      command=lambda _x, k=key, l=value_label: self._show_value(k, l)).pack(fill="x")
            self._show_value(key, value_label)

        buttons = ttk.Frame(panel, style="Panel.TFrame")
        buttons.pack(fill="x", pady=(10, 4))
        self.run_button = ttk.Button(buttons, text="▶ 开始", style="Accent.TButton", command=self.toggle)
        self.run_button.pack(side="left", fill="x", expand=True)
        ttk.Button(buttons, text="+1年", command=lambda: self.advance(1)).pack(side="left", padx=(5, 0))
        ttk.Button(buttons, text="+25年", command=lambda: self.advance(25)).pack(side="left", padx=(5, 0))
        actions = ttk.Frame(panel, style="Panel.TFrame")
        actions.pack(fill="x", pady=3)
        ttk.Button(actions, text="按当前设置重置", command=self.reset).pack(side="left", fill="x", expand=True)
        ttk.Button(actions, text="导出CSV", command=self.export).pack(side="left", padx=(5, 0))

    def _charts(self, parent: ttk.Frame) -> None:
        panel = ttk.Frame(parent, style="Panel.TFrame", padding=10)
        panel.grid(row=0, column=1, sticky="nsew", padx=(0, 8))
        panel.rowconfigure(1, weight=2)
        panel.rowconfigure(3, weight=2)
        panel.rowconfigure(5, weight=2)
        panel.columnconfigure(0, weight=1)
        ttk.Label(panel, text="人口与家户", style="Panel.TLabel",
                  font=("PingFang SC", 13, "bold")).grid(row=0, column=0, sticky="w", pady=(0, 5))
        self.demographic_canvas = tk.Canvas(panel, bg="#161c1e", highlightthickness=0)
        self.demographic_canvas.grid(row=1, column=0, sticky="nsew")
        self.demographic_canvas.bind("<Configure>", lambda _e: self.redraw())
        ttk.Label(panel, text="土地结构", style="Panel.TLabel",
                  font=("PingFang SC", 12, "bold")).grid(row=2, column=0, sticky="w", pady=(9, 4))
        self.land_canvas = tk.Canvas(panel, bg="#161c1e", highlightthickness=0)
        self.land_canvas.grid(row=3, column=0, sticky="nsew")
        ttk.Label(panel, text="家户土地持有分布（亩）", style="Panel.TLabel",
                  font=("PingFang SC", 12, "bold")).grid(row=4, column=0, sticky="w", pady=(9, 4))
        self.hist_canvas = tk.Canvas(panel, bg="#161c1e", highlightthickness=0)
        self.hist_canvas.grid(row=5, column=0, sticky="nsew")

    def _strategy_panel(self, parent: ttk.Frame) -> None:
        panel = ttk.Frame(parent, style="Panel.TFrame", padding=10)
        panel.grid(row=0, column=2, sticky="nsew")
        panel.rowconfigure(1, weight=2)
        panel.rowconfigure(3, weight=2)
        panel.rowconfigure(5, weight=2)
        panel.columnconfigure(0, weight=1)
        ttk.Label(panel, text="生存压力与集体行动", style="Panel.TLabel",
                  font=("PingFang SC", 13, "bold")).grid(row=0, column=0, sticky="w", pady=(0, 5))
        self.conflict_canvas = tk.Canvas(panel, bg="#161c1e", highlightthickness=0)
        self.conflict_canvas.grid(row=1, column=0, sticky="nsew")
        ttk.Label(panel, text="生存策略的人口加权均值", style="Panel.TLabel",
                  font=("PingFang SC", 12, "bold")).grid(row=2, column=0, sticky="w", pady=(9, 4))
        self.strategy_canvas = tk.Canvas(panel, bg="#161c1e", highlightthickness=0)
        self.strategy_canvas.grid(row=3, column=0, sticky="nsew")
        self.strategy_canvas.bind("<Configure>", lambda _e: self.redraw())
        self.strategy_text = ttk.Label(panel, text="", style="Panel.TLabel", justify="left")
        self.strategy_text.grid(row=4, column=0, sticky="ew", pady=(7, 3))
        self.inheritance_canvas = tk.Canvas(panel, bg="#161c1e", highlightthickness=0)
        self.inheritance_canvas.grid(row=5, column=0, sticky="nsew")

    def _show_value(self, key: str, label: ttk.Label) -> None:
        value = self.values[key].get()
        if key in {"subsistence", "reserve"}:
            label.configure(text=f"{value:.2f}")
        else:
            label.configure(text=f"{value:.1%}" if key in {"growth", "evasion"} else f"{value:.0%}")

    def _mode_help(self) -> None:
        text = ("所有家户使用相同策略，用于比较继承制、税率等制度。" if self.mode_var.get() == "fixed"
                else "初始策略随机；后代继承并小幅变异。后代占比就是策略适应度。")
        self.mode_help.configure(text=text)

    def _new_simulation(self) -> None:
        value = lambda key: self.values[key].get()
        institution = Institution(
            harvest_cv=value("harvest"),
            interest_rate=value("interest"),
            fiscal_burden=value("burden"),
            fiscal_growth=value("growth"),
            evasion_rate=value("evasion"),
            revolt_threshold=value("revolt"),
            war_seizure=value("seizure"),
            subsistence=value("subsistence"),
            inheritance="equal" if self.inheritance_var.get() == "均分继承" else "primogeniture",
        )
        strategy = Strategy(
            fertility=value("fertility"),
            reserve_years=value("reserve"),
            acquisition=value("acquisition"),
        )
        self.sim = AgrarianSimulation(seed=self.seed, mode=self.mode_var.get(), institution=institution,
                                      fixed_strategy=strategy,
                                      mutation_rate=value("mutation"))

    def reset(self) -> None:
        self.running = False
        self.run_button.configure(text="▶ 开始")
        self._new_simulation()
        self.redraw()

    def toggle(self) -> None:
        self.running = not self.running
        self.run_button.configure(text="Ⅱ 暂停" if self.running else "▶ 开始")
        if self.running:
            self._tick()

    def _tick(self) -> None:
        if not self.running:
            return
        self.advance(1)
        self.after(self.speed_ms, self._tick)

    def advance(self, years: int) -> None:
        self.sim.step(years)
        self.redraw()

    def export(self) -> None:
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=(("CSV", "*.csv"),),
                                            initialfile="agrarian_history.csv")
        if path:
            self.sim.export_csv(path)
            messagebox.showinfo("导出完成", path)

    def redraw(self) -> None:
        if not hasattr(self, "sim"):
            return
        m = self.sim.metrics()
        status = "战乱" if m["at_war"] else f"立国第 {m['dynasty_age']} 年"
        self.year_label.configure(
            text=f"第 {m['year']} 年 · 第 {m['dynasty']} 朝 · {status} · {self.sim.mode}")
        formats = {
            "population": f"{float(m['population']):,.0f}", "households": f"{m['households']}",
            "gini": f"{float(m['land_gini']):.3f}", "top": f"{float(m['top10_land']):.1%}",
            "landless": f"{float(m['landless_rate']):.1%}", "fiscal": f"{float(m['fiscal_ratio']):.0%}",
            "cycles": f"{m['cycles']}",
        }
        for key, value in formats.items(): self.kpis[key].set(value)
        self.event_label.configure(text="；".join(self.sim.events) if self.sim.events else (
            f"人均耕地 {float(m['land_per_person']):.1f} 亩　劳动收入 {float(m['wage']):.2f} 石/人　"
            f"地租 {float(m['rent']):.2f} 石/亩　亩税 {float(m['tax_per_mu']):.2f}　"
            f"地价 {float(m['land_price']):.1f}　抵债失地 {float(m['land_transferred']):.0f} 亩"))
        self._draw_demographic()
        self._draw_land()
        self._draw_conflict()
        self._draw_hist()
        self._draw_strategy()
        self._draw_inheritance()
        self.strategy_text.configure(text=(
            f"生育倾向 {float(m['fertility']):.3f}　存粮目标 {float(m['reserve_years']):.2f}年\n"
            f"放贷倾向 {float(m['acquisition']):.1%}　反抗阈值 {float(m['resistance_threshold']):.2f}"
        ))

    def _plot(self, canvas: tk.Canvas, series: list[tuple[str, str, str, bool]], shared: bool = False) -> None:
        canvas.delete("all")
        w, h = max(100, canvas.winfo_width()), max(100, canvas.winfo_height())
        left, right, top, bottom = 42, 15, 25, 25
        history = self.sim.history[-400:]
        canvas.create_line(left, h-bottom, w-right, h-bottom, fill="#566064")
        if len(history) < 2:
            canvas.create_text(w/2, h/2, text="推进时间后显示", fill=MUTED)
            return
        shared_values = [float(row[key]) for key, _c, _l, _f in series for row in history]
        shared_lo, shared_hi = min(shared_values), max(shared_values)
        for si, (key, color, label, fixed) in enumerate(series):
            vals = [float(row[key]) for row in history]
            lo, hi = ((0., 1.) if fixed else ((shared_lo, shared_hi) if shared else (min(vals), max(vals))))
            if hi - lo < 1e-9: hi = lo + 1
            pts = []
            for i, val in enumerate(vals):
                x = left + i / (len(vals)-1) * (w-left-right)
                y = top + (1-(val-lo)/(hi-lo)) * (h-top-bottom)
                pts += [x, y]
            canvas.create_line(*pts, fill=color, width=2, smooth=True)
            x = left + si * max(82, (w-left-right) / len(series))
            canvas.create_rectangle(x, 7, x+10, 17, fill=color, outline="")
            current = f"{vals[-1]:.1%}" if fixed else (f"{vals[-1]:,.0f}" if vals[-1] >= 100 else f"{vals[-1]:.2f}")
            canvas.create_text(x+14, 12, anchor="w", text=f"{label} {current}", fill=TEXT,
                               font=("PingFang SC", 8))

    def _draw_demographic(self) -> None:
        self._plot(self.demographic_canvas, [("population", GREEN, "人口", False),
                                              ("households", BLUE, "家户", False)], shared=True)

    def _draw_land(self) -> None:
        self._plot(self.land_canvas, [("land_gini", RED, "土地基尼", True),
                                      ("top10_land", GOLD, "前10%占地", True),
                                      ("landless_rate", BLUE, "无地人口", True),
                                      ("hidden_land", CYAN, "隐田", True)])

    def _draw_conflict(self) -> None:
        self._plot(self.conflict_canvas, [("hunger_rate", RED, "饥饿", True),
                                          ("mobilized", CYAN, "动员人口", True),
                                          ("uprising_pressure", GOLD, "起义压力", True),
                                          ("fiscal_ratio", GREEN, "财政充足", True)])

    def _draw_strategy(self) -> None:
        self._plot(self.strategy_canvas, [("fertility", GREEN, "生育", False),
                                           ("reserve_years", BLUE, "存粮", False),
                                           ("acquisition", GOLD, "放贷", True),
                                           ("resistance_threshold", RED, "反抗阈值", True)])

    def _draw_hist(self) -> None:
        c = self.hist_canvas; c.delete("all")
        w, h = max(100, c.winfo_width()), max(100, c.winfo_height())
        counts, cap = self.sim.land_histogram(bins=10)
        mx, bw = max(counts) or 1, (w-45)/len(counts)
        for i, count in enumerate(counts):
            bh = count/mx*(h-53)
            c.create_rectangle(34+i*bw, h-36-bh, 34+(i+1)*bw-1, h-36,
                               fill=RED if i < 3 else GREEN, outline="")
            low = i * cap / len(counts)
            high = (i + 1) * cap / len(counts)
            label = f"{low:.1f}–{high:.1f}" if i < len(counts)-1 else f"≥{low:.1f}"
            c.create_text(34+(i+.5)*bw, h-18, text=label, fill=MUTED,
                          font=("Menlo", 7), angle=25)

    def _draw_inheritance(self) -> None:
        c = self.inheritance_canvas; c.delete("all")
        w, h = max(100, c.winfo_width()), max(100, c.winfo_height())
        m = self.sim.metrics()
        equal = float(m["equal_inheritance"])
        x0, x1, y0, y1 = 12, w-12, 30, 66
        split = x0 + (x1-x0)*equal
        c.create_text(8, 8, anchor="nw", text="继承选择（按人口加权）", fill=TEXT,
                      font=("PingFang SC", 10, "bold"))
        if equal > 0:
            c.create_rectangle(x0, y0, split, y1, fill=CYAN, outline="")
        if equal < 1:
            c.create_rectangle(split, y0, x1, y1, fill=RED, outline="")
        if equal >= .16:
            c.create_text((x0+split)/2, (y0+y1)/2, text=f"均分 {equal:.1%}", fill="#101719",
                          font=("PingFang SC", 10, "bold"))
        else:
            c.create_text(x0, y1+10, anchor="w", text=f"均分 {equal:.1%}", fill=CYAN,
                          font=("PingFang SC", 8))
        if 1-equal >= .16:
            c.create_text((split+x1)/2, (y0+y1)/2, text=f"长子 {1-equal:.1%}", fill="#fff5e7",
                          font=("PingFang SC", 10, "bold"))
        else:
            c.create_text(x1, y1+10, anchor="e", text=f"长子 {1-equal:.1%}", fill=RED,
                          font=("PingFang SC", 8))
        shares = self.sim.lineage_shares()
        top = "　".join(f"#{lineage} {share:.1%}" for lineage, share in shares[:4])
        c.create_text(12, min(h-12, 90), anchor="nw", text=f"最大谱系：{top}", fill=MUTED,
                      font=("PingFang SC", 8), width=max(100, w-24))


def cli(args: argparse.Namespace) -> int:
    inst = Institution(inheritance=args.inheritance, fiscal_burden=args.fiscal_burden,
                       fiscal_growth=args.fiscal_growth, interest_rate=args.interest,
                       revolt_threshold=args.revolt_threshold, war_seizure=args.war_seizure)
    sim = AgrarianSimulation(households=args.households, seed=args.seed, mode=args.mode,
                             institution=inst, mutation_rate=args.mutation)
    falls = []
    for _ in range(args.years):
        sim.step(1)
        falls += [f"  第 {sim.year} 年　{event}" for event in sim.events]
    m = sim.metrics()
    print(f"模式: {args.mode}　年份: {m['year']}　第 {m['dynasty']} 朝　改朝 {m['cycles']} 次")
    print(f"人口: {float(m['population']):,.0f}　家户: {m['households']}　"
          f"人均耕地: {float(m['land_per_person']):.1f} 亩")
    print(f"土地基尼: {float(m['land_gini']):.3f}　前10%占地: {float(m['top10_land']):.1%}　"
          f"无地人口: {float(m['landless_rate']):.1%}")
    print(f"财政充足率: {float(m['fiscal_ratio']):.0%}　隐田: {float(m['hidden_land']):.1%}　"
          f"动员: {float(m['mobilized']):.1%}")
    print(f"策略均值: 生育={float(m['fertility']):.3f}, 存粮={float(m['reserve_years']):.2f}, "
          f"放贷={float(m['acquisition']):.2f}, 均分人口={float(m['equal_inheritance']):.1%}")
    if falls:
        print("朝代更替:")
        print("\n".join(falls))
    if args.csv:
        sim.export_csv(args.csv)
        print(f"已导出: {args.csv}")
    return 0


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="底层农业社会模拟")
    p.add_argument("--years", type=int, default=0)
    p.add_argument("--households", type=int, default=600)
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--mode", choices=("fixed", "evolution"), default="fixed")
    p.add_argument("--inheritance", choices=("equal", "primogeniture"), default="equal")
    p.add_argument("--fiscal-burden", type=float, default=.08)
    p.add_argument("--fiscal-growth", type=float, default=.007)
    p.add_argument("--interest", type=float, default=.40)
    p.add_argument("--revolt-threshold", type=float, default=.20)
    p.add_argument("--war-seizure", type=float, default=.15)
    p.add_argument("--mutation", type=float, default=.06)
    p.add_argument("--csv")
    return p.parse_args()


def launch() -> None:
    args = parse_args()
    if args.years:
        raise SystemExit(cli(args))
    ObserverApp(seed=args.seed).mainloop()


if __name__ == "__main__":
    launch()
