import pandas as pd
import random
import copy

print("🚀 เริ่มระบบ AI Scheduling (GA MASTER VERSION + Workload Balance + Multi-Run)...")

# ============================================================
# LOAD DATA
# ============================================================
groups    = pd.read_csv("student_group.csv")
subjects  = pd.read_csv("subject.csv")
teachers  = pd.read_csv("teacher.csv")
rooms     = pd.read_csv("room.csv")
timeslots = pd.read_csv("timeslot.csv")
teach     = pd.read_csv("teach.csv")
register  = pd.read_csv("register.csv")   # ✅ ใช้แทน group_subject.csv

print("💾 โหลดข้อมูลเรียบร้อยแล้ว!")

# ============================================================
# PREPARE GLOBAL REFERENCES  (NO group_subject.csv)
# ============================================================

# 1) คู่ subject_id → teacher_id ที่สอนได้
subject_teacher_pairs = teach[["subject_id", "teacher_id"]].values.tolist()

# 2) รวมชั่วโมงเรียนของแต่ละวิชา: theory + practice
#    (ถ้าคอลัมน์ชื่ออย่างอื่นให้แก้ตรงนี้)
subjects[["theory", "practice"]] = subjects[["theory", "practice"]].fillna(0)
subjects["hours"] = subjects["theory"] + subjects["practice"]
subject_hours = dict(zip(subjects["subject_id"], subjects["hours"]))

# 3) สร้างรายการ (group_id, subject_id, hours) จาก register + subject_hours
group_subjects = []
for _, row in register.iterrows():
    g = row["group_id"]
    s = row["subject_id"]
    h = int(subject_hours.get(s, 0))
    group_subjects.append((g, s, h))

# 4) ชั่วโมงเรียนที่ต้องสอนของแต่ละคู่ group–subject
required_hours = {(g, s): int(h) for g, s, h in group_subjects}

# 5) วิชาที่แต่ละกลุ่มลงทะเบียน
expected_subjects_by_group = {
    g: set(rows["subject_id"].tolist())
    for g, rows in register.groupby("group_id")
}

# 6) คาบทั้งหมดที่ต้องจัด
expected_total_hours = sum(required_hours.values())
print(f"🎯 จำนวนคาบรวม (จาก theory + practice) = {expected_total_hours}")

# ============================================================
# VALID TIMESLOTS
# ============================================================
valid_mask = (timeslots["period"] != 5) & (timeslots["period"] <= 10)
teaching_slots = timeslots[valid_mask][["day", "period"]].values.tolist()

# ============================================================
# HELPER
# ============================================================
def suggest_rooms(k=5):
    return random.sample(list(rooms["room_id"]), k=min(k, len(rooms)))

# ============================================================
# RANDOM INITIAL SCHEDULE
# ============================================================
def random_schedule():
    schedule = []
    used = set()
    group_day_load = {}

    for g, s, hours in group_subjects:
        teachers_allowed = [t for subj, t in subject_teacher_pairs if subj == s]
        if not teachers_allowed:
            print(f"⚠️ ไม่มีครูสำหรับวิชา {s}")
            continue

        for _ in range(int(hours)):
            assigned = False
            attempts = 0

            while not assigned and attempts < 300:
                t = random.choice(teachers_allowed)
                day, period = random.choice(teaching_slots)

                if group_day_load.get((g, day), 0) >= 10:
                    attempts += 1
                    continue

                for room in suggest_rooms(5):
                    tk = (t, day, period)
                    rk = (room, day, period)
                    gk = (g, day, period)

                    if tk not in used and rk not in used and gk not in used:
                        schedule.append({
                            "group_id": g,
                            "day": day,
                            "period": period,
                            "subject_id": s,
                            "teacher_id": t,
                            "room_id": room
                        })
                        used |= {tk, rk, gk}
                        group_day_load[(g, day)] = group_day_load.get((g, day), 0) + 1
                        assigned = True
                        break

                attempts += 1

            if not assigned:
                print(f"⚠️ Random Init: {g}-{s} ไม่ครบ {hours}")

    return schedule

# ============================================================
# FITNESS FUNCTION
# ============================================================
def fitness(schedule):
    if not schedule:
        return -1e9

    score = 0
    used = set()
    df = pd.DataFrame(schedule)

    # 1) conflict
    for e in schedule:
        tk = (e["teacher_id"], e["day"], e["period"])
        rk = (e["room_id"],   e["day"], e["period"])
        gk = (e["group_id"],  e["day"], e["period"])

        if tk not in used and rk not in used and gk not in used:
            score += 2
        else:
            score -= 50
        used |= {tk, rk, gk}

    # 2) ชั่วโมงเรียนต้องตรง
    gs = df.groupby(["group_id", "subject_id"]).size().to_dict()
    for key, req in required_hours.items():
        score -= abs(gs.get(key, 0) - req) * 25

    # 3) คาบรวม
    score -= abs(len(schedule) - expected_total_hours) * 40

    # 4) วิชาตรงทะเบียน
    for g in df["group_id"].unique():
        used_subs = set(df[df["group_id"] == g]["subject_id"].unique())
        expected = expected_subjects_by_group[g]
        score -= (len(expected - used_subs) + len(used_subs - expected)) * 80

    # 5) Bonus ต่อเนื่อง
    for (g, day), sub in df.groupby(["group_id", "day"]):
        sub_sorted = sub.sort_values("period")
        per = sub_sorted["period"].tolist()
        subs = sub_sorted["subject_id"].tolist()
        for i in range(len(per)-1):
            if per[i+1] == per[i] + 1 and subs[i] == subs[i+1]:
                score += 5

    # 6) Limit <= 10
    for cnt in df.groupby(["group_id", "day"]).size():
        if cnt > 10:
            score -= (cnt - 10) * 5000

    # 7) No period 5 / >10
    score -= (df["period"] == 5).sum() * 5000
    score -= (df["period"] > 10).sum() * 5000

    # 8) Workload Balance
    day_load = df.groupby(["group_id", "day"]).size()
    score -= sum([max(0, load - 8) * 30 for load in day_load])
    if len(day_load) > 0 and all(load >= 6 for load in day_load):
        score -= 300
    score -= sum([max(0, 3 - load) * 10 for load in day_load])

    return score

# ============================================================
# MUTATION
# ============================================================
def safe_mutation(child):
    if not child:
        return

    mutate = random.choice(child)
    g = mutate["group_id"]
    t = mutate["teacher_id"]
    r = mutate["room_id"]

    for _ in range(80):
        new_day, new_period = random.choice(teaching_slots)
        df_temp = pd.DataFrame(child)

        df_temp = df_temp[
            ~(
                (df_temp["group_id"] == g) &
                (df_temp["day"] == mutate["day"]) &
                (df_temp["period"] == mutate["period"]) &
                (df_temp["subject_id"] == mutate["subject_id"]) &
                (df_temp["teacher_id"] == t) &
                (df_temp["room_id"] == r)
            )
        ]

        if df_temp[(df_temp["group_id"] == g) & (df_temp["day"] == new_day)].shape[0] >= 10:
            continue
        if not df_temp[(df_temp["teacher_id"] == t) & (df_temp["day"] == new_day) &
                       (df_temp["period"] == new_period)].empty:
            continue
        if not df_temp[(df_temp["room_id"] == r) & (df_temp["day"] == new_day) &
                       (df_temp["period"] == new_period)].empty:
            continue
        if not df_temp[(df_temp["group_id"] == g) & (df_temp["day"] == new_day) &
                       (df_temp["period"] == new_period)].empty:
            continue

        mutate["day"] = new_day
        mutate["period"] = new_period
        return

# ============================================================
# HARD CONSTRAINT CHECKER
# ============================================================
def all_constraints_ok(schedule):
    df = pd.DataFrame(schedule)

    if len(df) != expected_total_hours:
        return False
    if (df["period"] == 5).sum() > 0:
        return False
    if (df["period"] > 10).sum() > 0:
        return False
    if df.groupby(["group_id", "day"]).size().max() > 10:
        return False

    gs = df.groupby(["group_id", "subject_id"]).size().to_dict()
    for key, req in required_hours.items():
        if gs.get(key, 0) != req:
            return False

    for g in df["group_id"].unique():
        used = set(df[df["group_id"] == g]["subject_id"].unique())
        if used != expected_subjects_by_group[g]:
            return False

    used_set = set()
    for e in schedule:
        tk = (e["teacher_id"], e["day"], e["period"])
        rk = (e["room_id"],   e["day"], e["period"])
        gk = (e["group_id"],  e["day"], e["period"])
        if tk in used_set or rk in used_set or gk in used_set:
            return False
        used_set |= {tk, rk, gk}

    return True

# ============================================================
# GA MULTI-RUN LOOP (20 RUNS)
# ============================================================
population_size = 60
generations = 250
num_runs = 20

print(f"⚙️ เริ่มรัน GA ทั้งหมด {num_runs} รอบ เพื่อหาตารางที่ดีที่สุด...")

overall_best = None
overall_best_score = float("-inf")
overall_best_run = -1
overall_best_gen = -1

for run in range(num_runs):
    print(f"\n🔁 RUN {run+1}/{num_runs}")
    population = [random_schedule() for _ in range(population_size)]

    for gen in range(generations):
        population.sort(key=fitness, reverse=True)
        best = population[0]
        best_score = fitness(best)

        if gen % 10 == 0:
            print(f"  GEN {gen:03d} | Fitness={best_score} | Slots={len(best)}")

        if all_constraints_ok(best):
            print(f"  🎉 RUN {run+1}: พบตารางสมบูรณ์ใน GEN {gen} | Fitness={best_score}")
            if best_score > overall_best_score:
                overall_best = copy.deepcopy(best)
                overall_best_score = best_score
                overall_best_run = run + 1
                overall_best_gen = gen
            break

        next_gen = population[:10]

        while len(next_gen) < population_size:
            p1, p2 = random.sample(population[:25], 2)
            if len(p1) == 0 or len(p2) == 0:
                continue
            cut = random.randint(0, min(len(p1), len(p2)) - 1)
            child = p1[:cut] + p2[cut:]
            if random.random() < 0.25:
                safe_mutation(child)
            next_gen.append(child)

        population = next_gen
    else:
        print(f"  ⚠️ RUN {run+1}: หมด {generations} GEN แล้วยังไม่เจอตารางที่ผ่าน Hard Constraints")

# ============================================================
# CHECK OVERALL BEST
# ============================================================
if overall_best is None:
    print("\n❌ ไม่พบตารางที่ผ่าน Hard Constraints ในทุก RUN")
    raise SystemExit()

print(f"\n🏆 เลือกใช้ตารางที่ดีที่สุดจาก RUN {overall_best_run} GEN {overall_best_gen} | Fitness={overall_best_score}")

best = overall_best

# ============================================================
# EXPORT RESULTS (NO day, NO period)
# ============================================================
best_df = pd.DataFrame(best)

# map timeslot_id จาก day, period
best_df = best_df.merge(
    timeslots[["timeslot_id", "day", "period"]],
    on=["day", "period"],
    how="left"
)

# ลบ day และ period ออกจากผลลัพธ์
best_df = best_df[[
    "group_id",
    "timeslot_id",
    "subject_id",
    "teacher_id",
    "room_id"
]].sort_values(["group_id", "timeslot_id"])

print("\n📅 FINAL TIMETABLE (BEST OVER ALL RUNS)")
print(best_df.to_string(index=False))

best_df.to_csv("timetable.csv", index=False, encoding="utf-8-sig")
print("💾 บันทึกแล้ว: timetable.csv")


# ============================================================
# SUMMARY REPORT BY GROUP (NO day, NO period)
# ============================================================
print("\n=============================")
print("📌 สรุปตารางเรียนรายกลุ่ม (Hours & Workload)")
print("=============================\n")

group_name_map = dict(zip(groups["group_id"], groups["group_name"]))

# dictionary: timeslot_id → day
slot_to_day = dict(zip(timeslots["timeslot_id"], timeslots["day"]))

day_order_internal = ["Mon", "Tue", "Wed", "Thu", "Fri"]
day_label_th = {
    "Mon": "จันทร์",
    "Tue": "อังคาร",
    "Wed": "พุธ",
    "Thu": "พฤหัส",
    "Fri": "ศุกร์"
}

for g in best_df["group_id"].unique():
    gname = group_name_map.get(g, g)
    g_data = best_df[best_df["group_id"] == g]

    # สร้างวันจาก timeslot_id
    g_data["day"] = g_data["timeslot_id"].map(slot_to_day)

    total_hours = len(g_data)
    day_load = g_data.groupby("day").size().to_dict()

    print(f"🎓 กลุ่ม: {gname}")
    print(f"- ชั่วโมงเรียนรวมทั้งหมด: {total_hours} ชม.")
    print("- ตารางเรียนรายวัน:")

    for d in day_order_internal:
        th_label = day_label_th.get(d, d)
        cnt = day_load.get(d, 0)
        print(f"   • {th_label:<7} : {cnt} คาบ")

    print()

