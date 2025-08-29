// displayId.test.ts - Test cases to demonstrate the corrected logic

import { getDisplayId, extractDisplayIds, PersonData } from './displayId';

// 模拟测试数据
const testPersons: PersonData[] = [
  // 球员1: OCR识别到jersey 10，ByteSort track_id 1
  {
    track_id: 1,
    jersey_number: "10",
    jersey_confidence: 0.9,
    pose: [[100, 100], [110, 110]],
    speed_kmh: 15.5
  },
  // 球员2: OCR识别到jersey 23，ByteSort track_id 5
  {
    track_id: 5,
    jersey_number: "23", 
    jersey_confidence: 0.85,
    pose: [[200, 200], [210, 210]],
    speed_kmh: 12.3
  },
  // 球员3: OCR识别到jersey 7，但置信度太低，ByteSort track_id 3
  {
    track_id: 3,
    jersey_number: "7",
    jersey_confidence: 0.5,
    pose: [[300, 300], [310, 310]],
    speed_kmh: 18.2
  },
  // 球员4: 没有OCR识别到jersey，只有ByteSort track_id 2
  {
    track_id: 2,
    pose: [[400, 400], [410, 410]], 
    speed_kmh: 9.8
  },
  // 球员5: OCR识别到jersey 99，ByteSort track_id 10
  {
    track_id: 10,
    jersey_number: "99",
    jersey_confidence: 0.95,
    pose: [[500, 500], [510, 510]],
    speed_kmh: 22.1
  }
];

console.log("=== Display ID System Test ===\n");

testPersons.forEach((person, index) => {
  const displayId = getDisplayId(person, 0.7);
  console.log(`Person ${index + 1}:`);
  console.log(`  Track ID: ${person.track_id}`);
  console.log(`  Jersey Number: ${person.jersey_number || 'N/A'}`);
  console.log(`  Jersey Confidence: ${person.jersey_confidence || 'N/A'}`);
  console.log(`  ➜ Display ID: ${displayId.id}`);
  console.log(`  ➜ Display Value: ${displayId.displayValue} (REAL ${displayId.type === 'jersey' ? 'jersey number' : 'track ID'})`);
  console.log(`  ➜ Label: ${displayId.label}`);
  console.log(`  ➜ Type: ${displayId.type}`);
  console.log("");
});

const extractedIds = extractDisplayIds(testPersons, 0.7);
console.log("=== Extracted Display IDs (sorted: jersey first, then by real value) ===");
extractedIds.forEach((displayId, index) => {
  console.log(`${index + 1}. ${displayId.label} (${displayId.id}) - Real Value: ${displayId.displayValue}`);
});

console.log("\n=== Expected Results ===");
console.log("✅ Jersey 7 (jersey_7) - Real jersey number: 7");  
console.log("✅ Jersey 10 (jersey_10) - Real jersey number: 10");
console.log("✅ Jersey 23 (jersey_23) - Real jersey number: 23");
console.log("✅ Jersey 99 (jersey_99) - Real jersey number: 99");
console.log("✅ Track 2 (track_2) - Real track ID: 2"); 
console.log("✅ Track 3 (track_3) - Real track ID: 3 (jersey 7 confidence too low)");

export {};