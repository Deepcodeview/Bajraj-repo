import prisma from "../src/config/database.js";

// ── Fetch existing org and store ──────────────────────────────────────────────
const org   = await prisma.organizations.findFirst();
const store = await prisma.stores.findFirst({ where: { organization_id: org.id } });

if (!org || !store) {
  console.error("No organization or store found. Please create them first.");
  process.exit(1);
}

const ORG_ID   = org.id;
const STORE_ID = store.id;
const TODAY    = new Date();

console.log(`Seeding for org: ${org.name} | store: ${store.name}`);

// ── Products ──────────────────────────────────────────────────────────────────
const productData = [
  { sku: "ELEC-001", name: "Samsung 55\" Smart TV",     category: "Electronics",  unit: "pcs" },
  { sku: "ELEC-002", name: "Sony Bluetooth Speaker",    category: "Electronics",  unit: "pcs" },
  { sku: "CLTH-001", name: "Men's Formal Shirt",        category: "Clothing",     unit: "pcs" },
  { sku: "CLTH-002", name: "Women's Kurti",             category: "Clothing",     unit: "pcs" },
  { sku: "GROC-001", name: "Basmati Rice 5kg",          category: "Groceries",    unit: "bag" },
  { sku: "GROC-002", name: "Sunflower Oil 1L",          category: "Groceries",    unit: "bottle" },
  { sku: "APPL-001", name: "Prestige Pressure Cooker",  category: "Appliances",   unit: "pcs" },
  { sku: "APPL-002", name: "Philips Air Fryer",         category: "Appliances",   unit: "pcs" },
];

const products = [];
for (const p of productData) {
  const existing = await prisma.products.findFirst({ where: { organization_id: ORG_ID, sku: p.sku } });
  if (existing) {
    products.push(existing);
  } else {
    const created = await prisma.products.create({ data: { organization_id: ORG_ID, ...p } });
    products.push(created);
  }
}
console.log(`✔ Products ready (${products.length})`);

// ── Customer Sessions (today) ─────────────────────────────────────────────────
const sessionCount = 15;
const sessions = [];
for (let i = 0; i < sessionCount; i++) {
  const startHour  = 9 + Math.floor(Math.random() * 9);
  const startMin   = Math.floor(Math.random() * 60);
  const durationMin = 10 + Math.floor(Math.random() * 50);
  const startTime  = new Date(TODAY);
  startTime.setHours(startHour, startMin, 0, 0);
  const endTime = new Date(startTime.getTime() + durationMin * 60000);

  const session = await prisma.customer_sessions.create({
    data: {
      organization_id:      ORG_ID,
      store_id:             STORE_ID,
      session_code:         `SESS-TODAY-${Date.now()}-${i}`,
      customer_tracking_id: `CUST-${1000 + i}`,
      start_time:           startTime,
      end_time:             endTime,
      status:               "COMPLETED",
    },
  });
  sessions.push(session);
}
console.log(`✔ Customer sessions created (${sessions.length})`);

// ── Transactions + Items + Payments (today) ───────────────────────────────────
const paymentModes = ["CASH", "CARD", "UPI", "WALLET"];
const txnCount = 12;

for (let i = 0; i < txnCount; i++) {
  const session    = sessions[i % sessions.length];
  const txnHour    = 9 + Math.floor(Math.random() * 9);
  const txnTime    = new Date(TODAY);
  txnTime.setHours(txnHour, Math.floor(Math.random() * 60), 0, 0);

  // Pick 1-3 random products
  const itemCount    = 1 + Math.floor(Math.random() * 3);
  const chosenProds  = [...products].sort(() => 0.5 - Math.random()).slice(0, itemCount);

  const prices = { "ELEC-001": 45000, "ELEC-002": 3500, "CLTH-001": 1200, "CLTH-002": 900, "GROC-001": 350, "GROC-002": 180, "APPL-001": 2800, "APPL-002": 6500 };

  let subtotal = 0;
  const itemsPayload = chosenProds.map(p => {
    const qty   = 1 + Math.floor(Math.random() * 3);
    const price = prices[p.sku] || 500;
    const total = qty * price;
    subtotal   += total;
    return { product_id: p.id, sku: p.sku, product_name: p.name, quantity: qty, unit_price: price, total_price: total };
  });

  const discount = Math.random() > 0.7 ? Math.round(subtotal * 0.05) : 0;
  const tax      = Math.round((subtotal - discount) * 0.18);
  const total    = subtotal - discount + tax;

  const txn = await prisma.transactions.create({
    data: {
      organization_id:      ORG_ID,
      store_id:             STORE_ID,
      customer_session_id:  session.id,
      transaction_code:     `TXN-TODAY-${Date.now()}-${i}`,
      subtotal_amount:      subtotal,
      discount_amount:      discount,
      tax_amount:           tax,
      total_amount:         total,
      currency:             "INR",
      status:               "COMPLETED",
      transaction_timestamp: txnTime,
      source_system:        "POS",
    },
  });

  // Transaction items
  for (const item of itemsPayload) {
    await prisma.transaction_items.create({
      data: { organization_id: ORG_ID, transaction_id: txn.id, ...item },
    });
  }

  // Payment
  const mode = paymentModes[Math.floor(Math.random() * paymentModes.length)];
  await prisma.payments.create({
    data: {
      organization_id:   ORG_ID,
      transaction_id:    txn.id,
      payment_mode:      mode,
      amount:            total,
      currency:          "INR",
      status:            "SUCCESS",
      payment_timestamp: txnTime,
      source_system:     "POS",
    },
  });
}

console.log(`✔ Transactions, items & payments created (${txnCount})`);
console.log("\n✅ Dummy sales data seeded successfully!");
console.log(`   Org ID:   ${ORG_ID}`);
console.log(`   Store ID: ${STORE_ID}`);

await prisma.$disconnect();
