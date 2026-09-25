import tkinter as tk
from tkinter import ttk, messagebox
import sqlite3
from datetime import date, datetime, timedelta

DB_FILE = "smart_fridge.db"

CATEGORIES = ["肉類", "蔬菜", "水果", "乳製品", "蛋類", "海鮮", "飲料", "調味料", "冷凍食品", "其他"]
LOCATIONS = ["冷藏", "冷凍", "蔬果室", "其他"]

def db():
    return sqlite3.connect(DB_FILE)

def init_db():
    con = db()
    cur = con.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS foods(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        barcode TEXT,
        name TEXT NOT NULL,
        category TEXT,
        quantity REAL DEFAULT 0,
        unit TEXT,
        location TEXT,
        purchase_date TEXT,
        open_date TEXT,
        expiry_date TEXT,
        note TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS transactions(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        food_id INTEGER,
        action TEXT,
        quantity REAL,
        trans_date TEXT,
        note TEXT
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS shopping_list(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        quantity REAL DEFAULT 1,
        unit TEXT,
        status INTEGER DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    con.commit()
    con.close()

class App:
    def __init__(self, root):
        self.root = root
        self.root.title("🧊 智慧冰箱 V1 (含取出紀錄)")
        self.root.geometry("1150x720")
        self.selected_id = None
        self.build_ui()
        self.refresh()

    def build_ui(self):
        top = ttk.Frame(self.root, padding=10)
        top.pack(fill="x")
        ttk.Label(top, text="🧊 智慧冰箱 V1", font=("Microsoft JhengHei", 20, "bold")).pack(side="left")
        ttk.Button(top, text="重新整理", command=self.refresh).pack(side="right")

        nb = ttk.Notebook(self.root)
        nb.pack(fill="both", expand=True, padx=10, pady=(0,10))
        self.nb = nb

        self.food_tab = ttk.Frame(nb)
        self.shopping_tab = ttk.Frame(nb)
        self.report_tab = ttk.Frame(nb)
        self.history_tab = ttk.Frame(nb)  # 新增：取出/異動紀錄分頁
        
        nb.add(self.food_tab, text="食材庫存")
        nb.add(self.shopping_tab, text="採買清單")
        nb.add(self.report_tab, text="到期/統計")
        nb.add(self.history_tab, text="取出/異動紀錄")

        self.build_food_tab()
        self.build_shopping_tab()
        self.build_report_tab()
        self.build_history_tab()

    def build_food_tab(self):
        form = ttk.LabelFrame(self.food_tab, text="食材資料", padding=10)
        form.pack(fill="x", padx=5, pady=5)

        labels = ["條碼", "食材名稱*", "分類", "數量", "單位", "位置", "購買日", "開封日", "到期日", "備註"]
        self.vars = {x: tk.StringVar() for x in labels}
        for i, lab in enumerate(labels):
            r, c = divmod(i, 5)
            ttk.Label(form, text=lab).grid(row=r*2, column=c*2, sticky="w", padx=4, pady=2)
            if lab == "分類":
                w = ttk.Combobox(form, textvariable=self.vars[lab], values=CATEGORIES, state="readonly", width=13)
            elif lab == "位置":
                w = ttk.Combobox(form, textvariable=self.vars[lab], values=LOCATIONS, state="readonly", width=13)
            else:
                w = ttk.Entry(form, textvariable=self.vars[lab], width=16)
            w.grid(row=r*2+1, column=c*2, columnspan=2, sticky="ew", padx=4, pady=2)

        btns = ttk.Frame(form)
        btns.grid(row=4, column=0, columnspan=10, sticky="w", pady=8)
        ttk.Button(btns, text="新增", command=self.add_food).pack(side="left", padx=3)
        ttk.Button(btns, text="修改", command=self.update_food).pack(side="left", padx=3)
        ttk.Button(btns, text="刪除", command=self.delete_food).pack(side="left", padx=3)
        ttk.Button(btns, text="使用/消耗", command=self.consume_food).pack(side="left", padx=3)
        ttk.Button(btns, text="清空", command=self.clear_form).pack(side="left", padx=3)
        ttk.Button(btns, text="加入採買清單", command=self.add_selected_to_shopping).pack(side="left", padx=3)

        search = ttk.Frame(self.food_tab, padding=5)
        search.pack(fill="x")
        ttk.Label(search, text="搜尋：").pack(side="left")
        self.search_var = tk.StringVar()
        e = ttk.Entry(search, textvariable=self.search_var, width=30)
        e.pack(side="left", padx=5)
        e.bind("<Return>", lambda _: self.refresh())
        ttk.Button(search, text="搜尋", command=self.refresh).pack(side="left")
        ttk.Button(search, text="全部", command=lambda: [self.search_var.set(""), self.refresh()]).pack(side="left", padx=4)

        cols = ("id","barcode","name","category","quantity","unit","location","purchase","open","expiry","status")
        self.tree = ttk.Treeview(self.food_tab, columns=cols, show="headings", height=16)
        heads = {
            "id":"ID","barcode":"條碼","name":"食材","category":"分類","quantity":"數量",
            "unit":"單位","location":"位置","purchase":"購買日","open":"開封日",
            "expiry":"到期日","status":"狀態"
        }
        widths = {"id":45,"barcode":110,"name":130,"category":85,"quantity":65,"unit":60,
                  "location":75,"purchase":90,"open":90,"expiry":90,"status":100}
        for c in cols:
            self.tree.heading(c, text=heads[c])
            self.tree.column(c, width=widths[c], anchor="center")
        self.tree.pack(fill="both", expand=True, padx=5, pady=5)
        self.tree.bind("<<TreeviewSelect>>", self.select_food)

    def build_shopping_tab(self):
        form = ttk.Frame(self.shopping_tab, padding=10)
        form.pack(fill="x")
        self.shop_name = tk.StringVar()
        self.shop_qty = tk.StringVar(value="1")
        self.shop_unit = tk.StringVar(value="個")
        ttk.Label(form, text="品項").pack(side="left")
        ttk.Entry(form, textvariable=self.shop_name, width=25).pack(side="left", padx=5)
        ttk.Label(form, text="數量").pack(side="left")
        ttk.Entry(form, textvariable=self.shop_qty, width=8).pack(side="left", padx=5)
        ttk.Label(form, text="單位").pack(side="left")
        ttk.Entry(form, textvariable=self.shop_unit, width=8).pack(side="left", padx=5)
        ttk.Button(form, text="新增", command=self.add_shopping).pack(side="left", padx=5)
        ttk.Button(form, text="已購買", command=self.mark_bought).pack(side="left", padx=5)
        ttk.Button(form, text="刪除", command=self.delete_shopping).pack(side="left", padx=5)

        cols = ("id","name","quantity","unit","status","created")
        self.shop_tree = ttk.Treeview(self.shopping_tab, columns=cols, show="headings")
        heads = {"id":"ID","name":"品項","quantity":"數量","unit":"單位","status":"狀態","created":"建立時間"}
        for c in cols:
            self.shop_tree.heading(c, text=heads[c])
            self.shop_tree.column(c, width=150, anchor="center")
        self.shop_tree.pack(fill="both", expand=True, padx=10, pady=10)

    def build_report_tab(self):
        self.report_text = tk.Text(self.report_tab, font=("Microsoft JhengHei", 12), wrap="word")
        self.report_text.pack(fill="both", expand=True, padx=10, pady=10)
        ttk.Button(self.report_tab, text="重新產生報表", command=self.refresh_report).pack(pady=(0,10))

    def build_history_tab(self):
        # 新增：建立取出/異動紀錄的介面
        top_frame = ttk.Frame(self.history_tab, padding=10)
        top_frame.pack(fill="x")
        ttk.Label(top_frame, text="📜 食材進出與取出紀錄清單", font=("Microsoft JhengHei", 14, "bold")).pack(side="left")
        ttk.Button(top_frame, text="重新整理紀錄", command=self.refresh_history).pack(side="right")

        cols = ("id", "food_name", "action", "quantity", "trans_date", "note")
        self.history_tree = ttk.Treeview(self.history_tab, columns=cols, show="headings", height=20)
        heads = {
            "id": "紀錄 ID", "food_name": "食材名稱", "action": "動作類型", 
            "quantity": "異動數量", "trans_date": "異動日期", "note": "備註說明"
        }
        widths = {"id": 70, "name": 150, "action": 90, "quantity": 90, "trans_date": 120, "note": 250}
        for c in cols:
            self.history_tree.heading(c, text=heads[c])
            self.history_tree.column(c, width=widths.get(c, 100), anchor="center")
        self.history_tree.pack(fill="both", expand=True, padx=10, pady=10)

    def add_food(self):
        v = self.vars
        if not v["食材名稱*"].get().strip():
            messagebox.showwarning("提醒", "請輸入食材名稱")
            return
        try:
            qty = float(v["數量"].get() or 0)
        except ValueError:
            messagebox.showwarning("提醒", "數量必須是數字")
            return
        con = db()
        cur = con.cursor()
        cur.execute("""INSERT INTO foods
            (barcode,name,category,quantity,unit,location,purchase_date,open_date,expiry_date,note)
            VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (v["條碼"].get(),v["食材名稱*"].get(),v["分類"].get(),qty,v["單位"].get(),
             v["位置"].get(),v["購買日"].get(),v["開封日"].get(),v["到期日"].get(),v["備註"].get()))
        fid = cur.lastrowid
        cur.execute("INSERT INTO transactions(food_id,action,quantity,trans_date,note) VALUES(?,?,?,?,?)",
                    (fid,"入庫",qty,date.today().isoformat(),"新增食材"))
        con.commit(); con.close()
        self.clear_form(); self.refresh()

    def update_food(self):
        if not self.selected_id:
            messagebox.showwarning("提醒","請先選擇食材")
            return
        v = self.vars
        try: qty = float(v["數量"].get() or 0)
        except ValueError:
            messagebox.showwarning("提醒","數量必須是數字"); return
        con = db(); cur = con.cursor()
        cur.execute("""UPDATE foods SET barcode=?,name=?,category=?,quantity=?,unit=?,location=?,
                       purchase_date=?,open_date=?,expiry_date=?,note=? WHERE id=?""",
                    (v["條碼"].get(),v["食材名稱*"].get(),v["分類"].get(),qty,v["單位"].get(),
                     v["位置"].get(),v["購買日"].get(),v["開封日"].get(),v["到期日"].get(),v["備註"].get(),self.selected_id))
        con.commit(); con.close(); self.refresh()

    def delete_food(self):
        if not self.selected_id: return
        if not messagebox.askyesno("確認","確定刪除這筆食材？"): return
        con=db(); cur=con.cursor()
        cur.execute("DELETE FROM foods WHERE id=?",(self.selected_id,))
        cur.execute("DELETE FROM transactions WHERE food_id=?",(self.selected_id,))
        con.commit(); con.close(); self.clear_form(); self.refresh()

    def consume_food(self):
        if not self.selected_id:
            messagebox.showwarning("提醒", "請先從上方清單選擇要消耗/取出的食材")
            return
        qty = tk.simpledialog.askfloat("使用/消耗", "請輸入取出/消耗數量：", minvalue=0.01)
        if qty is None: return
        con=db(); cur=con.cursor()
        cur.execute("SELECT quantity,name FROM foods WHERE id=?",(self.selected_id,))
        row=cur.fetchone()
        if not row: con.close(); return
        old,name=row
        if qty > old:
            messagebox.showwarning("提醒",f"{name} 目前庫存只有 {old}")
            con.close(); return
        newq=old-qty
        cur.execute("UPDATE foods SET quantity=? WHERE id=?",(newq,self.selected_id))
        # 寫入異動紀錄（取出情況）
        cur.execute("INSERT INTO transactions(food_id,action,quantity,trans_date,note) VALUES(?,?,?,?,?)",
                    (self.selected_id,"取出/消耗",-qty,date.today().isoformat(),"日常使用取出"))
        con.commit(); con.close(); self.refresh()
        messagebox.success = messagebox.showinfo("提示", f"成功從冰箱取出 {name} 共 {qty}！")

    def add_selected_to_shopping(self):
        if not self.selected_id: return
        con=db(); cur=con.cursor()
        cur.execute("SELECT name,unit FROM foods WHERE id=?",(self.selected_id,))
        row=cur.fetchone()
        if row:
            cur.execute("INSERT INTO shopping_list(name,quantity,unit) VALUES(?,?,?)",(row[0],1,row[1]))
            con.commit()
        con.close(); self.refresh_shopping()

    def select_food(self, _=None):
        sel=self.tree.selection()
        if not sel: return
        vals=self.tree.item(sel[0],"values")
        self.selected_id=int(vals[0])
        con=db(); cur=con.cursor()
        cur.execute("SELECT barcode,name,category,quantity,unit,location,purchase_date,open_date,expiry_date,note FROM foods WHERE id=?",(self.selected_id,))
        row=cur.fetchone(); con.close()
        if row:
            for k,val in zip(["條碼","食材名稱*","分類","數量","單位","位置","購買日","開封日","到期日","備註"],row):
                self.vars[k].set("" if val is None else str(val))

    def clear_form(self):
        self.selected_id=None
        for v in self.vars.values(): v.set("")

    def parse_date(self, value):
        if value is None: return None
        s = str(value).strip()
        if not s: return None
        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%Y%m%d"):
            try: return datetime.strptime(s, fmt).date()
            except ValueError: pass
        for sep in ("-", "/", "."):
            parts = s.split(sep)
            if len(parts) == 3:
                try:
                    y, m, d = map(int, parts)
                    return date(y, m, d)
                except ValueError: pass
        return None

    def status(self, expiry, qty):
        if qty <= 0: return "🔴 已用完"
        if not expiry: return "正常"
        d = self.parse_date(expiry)
        if d is None: return "日期格式錯誤"
        days=(d-date.today()).days
        if days < 0: return "🔴 已過期"
        if days == 0: return "🔴 今天到期"
        if days <= 3: return f"🟠 {days}天內到期"
        if days <= 7: return f"🟡 {days}天內到期"
        return "正常"

    def refresh(self):
        self.refresh_foods()
        self.refresh_shopping()
        self.refresh_report()
        self.refresh_history()

    def refresh_foods(self):
        for x in self.tree.get_children(): self.tree.delete(x)
        q=self.search_var.get().strip() if hasattr(self,"search_var") else ""
        con=db(); cur=con.cursor()
        if q:
            cur.execute("""SELECT id,barcode,name,category,quantity,unit,location,purchase_date,open_date,expiry_date
                           FROM foods WHERE name LIKE ? OR barcode LIKE ? OR category LIKE ? OR location LIKE ?
                           ORDER BY expiry_date""",(f"%{q}%",)*4)
        else:
            cur.execute("""SELECT id,barcode,name,category,quantity,unit,location,purchase_date,open_date,expiry_date
                           FROM foods ORDER BY expiry_date""")
        rows=cur.fetchall(); con.close()
        for r in rows:
            st=self.status(r[9],r[4])
            self.tree.insert("", "end", values=r+(st,))

    def refresh_shopping(self):
        if not hasattr(self,"shop_tree"): return
        for x in self.shop_tree.get_children(): self.shop_tree.delete(x)
        con=db(); cur=con.cursor()
        cur.execute("SELECT id,name,quantity,unit,status,created_at FROM shopping_list ORDER BY status,id DESC")
        for r in cur.fetchall():
            self.shop_tree.insert("", "end", values=r[:-2]+(("已購買" if r[4] else "待購買"),r[5]))
        con.close()

    def refresh_history(self):
        if not hasattr(self, "history_tree"): return
        for x in self.history_tree.get_children(): self.history_tree.delete(x)
        con = db(); cur = con.cursor()
        # 查詢交易紀錄並對應食材名稱
        cur.execute("""
            SELECT t.id, COALESCE(f.name, '(已刪除食材)'), t.action, t.quantity, t.trans_date, t.note
            FROM transactions t
            LEFT JOIN foods f ON t.food_id = f.id
            ORDER BY t.id DESC
        """)
        rows = cur.fetchall()
        con.close()
        for r in rows:
            self.history_tree.insert("", "end", values=r)

    def add_shopping(self):
        name=self.shop_name.get().strip()
        if not name: return
        try: qty=float(self.shop_qty.get() or 1)
        except ValueError: qty=1
        con=db(); con.execute("INSERT INTO shopping_list(name,quantity,unit) VALUES(?,?,?)",
                              (name,qty,self.shop_unit.get())); con.commit(); con.close()
        self.shop_name.set(""); self.refresh_shopping()

    def mark_bought(self):
        sel=self.shop_tree.selection()
        if not sel: return
        sid=int(self.shop_tree.item(sel[0],"values")[0])
        con=db(); con.execute("UPDATE shopping_list SET status=1 WHERE id=?",(sid,)); con.commit(); con.close()
        self.refresh_shopping()

    def delete_shopping(self):
        sel=self.shop_tree.selection()
        if not sel: return
        sid=int(self.shop_tree.item(sel[0],"values")[0])
        con=db(); con.execute("DELETE FROM shopping_list WHERE id=?",(sid,)); con.commit(); con.close()
        self.refresh_shopping()

    def refresh_report(self):
        if not hasattr(self,"report_text"): return
        con=db(); cur=con.cursor()
        cur.execute("SELECT COUNT(*), COALESCE(SUM(quantity),0) FROM foods")
        count,total=cur.fetchone()
        cur.execute("SELECT name,quantity,unit,expiry_date FROM foods WHERE expiry_date<>'' AND expiry_date IS NOT NULL ORDER BY expiry_date")
        rows=cur.fetchall()
        con.close()
        lines=[f"智慧冰箱報表  {datetime.now().strftime('%Y-%m-%d %H:%M')}",
               "",f"食材品項數：{count}",f"總數量：{total:g}","",
               "【保存期限提醒】"]
        found=False
        for name,qty,unit,exp in rows:
            st=self.status(exp,qty)
            if "到期" in st or "過期" in st:
                lines.append(f"{st}  {name} {qty:g}{unit or ''}（{exp}）")
                found=True
        if not found: lines.append("目前沒有 7 天內到期或已過期的食材。")
        self.report_text.delete("1.0","end"); self.report_text.insert("1.0","\n".join(lines))

if __name__ == "__main__":
    import tkinter.simpledialog
    init_db()
    root=tk.Tk()
    App(root)
    root.mainloop()
