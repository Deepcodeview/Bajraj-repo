const _stockReports = [];
let   _stockReportId = 1;

export function saveStockReport(data) {
  const record = {
    id:             _stockReportId++,
    cameraId:       data.cameraId,
    status:         data.status,
    occupancy:      data.occupancy,
    outOfStock:     data.outOfStock,
    emptyZones:     data.emptyZones,
    reducedZones:   data.reducedZones,
    labelCounts:    data.labelCounts || {},
    screenshotPath: data.screenshotPath || null,
    detectedAt:     data.detectedAt || new Date().toISOString(),
    date:           data.date,
    time:           data.time,
    createdAt:      new Date().toISOString(),
  };
  _stockReports.unshift(record);
  if (_stockReports.length > 200) _stockReports.pop();
  return record;
}

export function getStockReports({ cameraId, status, date, page = 1, limit = 20 }) {
  let list = [..._stockReports];
  if (cameraId) list = list.filter(r => r.cameraId === cameraId);
  if (status)   list = list.filter(r => r.status === status);
  if (date)     list = list.filter(r => r.date === date);
  const total = list.length;
  const data  = list.slice((page - 1) * limit, page * limit);
  return { total, page, limit, reports: data };
}

export function getStockReportSummary() {
  const today     = new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Kolkata" });
  const todayList = _stockReports.filter(r => r.date === today);
  const empty     = _stockReports.filter(r => r.status === "EMPTY").length;
  const lowStock  = _stockReports.filter(r => r.status === "LOW STOCK").length;
  return {
    total:          _stockReports.length,
    todayCount:     todayList.length,
    emptyCount:     empty,
    lowStockCount:  lowStock,
    lastDetected:   _stockReports[0] || null,
  };
}
