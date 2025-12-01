// ----------------- IMPORT -----------------
const express = require("express");
const admin = require("firebase-admin");
const fs = require("fs");
const csv = require("csv-parser");
const path = require("path");



const app = express();
const PORT = 5000;

// ----------------- INITIALIZE FIREBASE -----------------
const serviceAccount = require("./key1.json");

admin.initializeApp({
  credential: admin.credential.cert(serviceAccount),
  databaseURL: "https://autotimetable-382ee-default-rtdb.asia-southeast1.firebasedatabase.app/"
});

const db = admin.database();

// ----------------- รายชื่อไฟล์ CSV -----------------
const csvFiles = [
  { file: "teacher.csv", table: "teachers" },
  { file: "subject.csv", table: "subjects" },
  { file: "student_group.csv", table: "groups" },
  { file: "room.csv", table: "rooms" },
  { file: "timeslot.csv", table: "timeslots" },
];

// ----------------- ฟังก์ชัน Import CSV → Firebase -----------------
function importCSV(filePath, tableName) {
  return new Promise((resolve, reject) => {
    const rows = [];

    if (!fs.existsSync(filePath)) {
      console.warn(`⚠️ ไม่พบไฟล์: ${filePath}`);
      return resolve();
    }

    fs.createReadStream(filePath)
      .pipe(csv())
      .on("data", (data) => rows.push(data))
      .on("end", async () => {
        try {
          await db.ref(tableName).set(rows);
          console.log(`✅ Imported: ${filePath} → /${tableName} (${rows.length} rows)`);
          resolve();
        } catch (err) {
          console.error("❌ Firebase Error:", err);
          reject(err);
        }
      })
      .on("error", (err) => reject(err));
  });
}

// ----------------- ฟังก์ชัน Import ทั้งหมด -----------------
async function importAllCSV() {
  console.log("🚀 เริ่มนำเข้า CSV ทั้งหมด...");
  for (const item of csvFiles) {
    // ใช้ path folder dataset
    const filePath = path.join(__dirname, "dataset", item.file);
    await importCSV(filePath, item.table);
  }
  console.log("🎉 อัปโหลดทุกไฟล์เสร็จสมบูรณ์!");
}

// ----------------- Start Server และ Import CSV อัตโนมัติ -----------------
app.get("/", (req, res) => {
  res.send("🟢 Server is running!");
});

app.listen(PORT, async () => {
  console.log(`🚀 Server running at http://localhost:${PORT}`);

  // รัน import CSV อัตโนมัติทันที
  try {
    await importAllCSV();
    console.log("🎉 Initial CSV import done!");
  } catch (err) {
    console.error("❌ Error during initial CSV import:", err);
  }
});
