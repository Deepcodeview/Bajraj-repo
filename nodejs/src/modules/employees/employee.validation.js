const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const TIME_PATTERN = /^([01]\d|2[0-3]):[0-5]\d(:[0-5]\d)?$/;

function validateCommonFields(req, res, next, { partial = false } = {}) {
	const { storeId, employeeCode, firstName, email, shiftStart, shiftEnd, status } = req.body;

	if (!partial && (!storeId || !employeeCode || !firstName)) {
		return res.status(400).json({ success: false, message: "Store ID, employee code, and first name are required" });
	}
	if (storeId !== undefined && (!storeId || !UUID_PATTERN.test(storeId))) {
		return res.status(400).json({ success: false, message: "A valid store ID is required" });
	}
	if (employeeCode !== undefined && (!employeeCode || typeof employeeCode !== "string")) {
		return res.status(400).json({ success: false, message: "Employee code must be a non-empty string" });
	}
	if (firstName !== undefined && (!firstName || typeof firstName !== "string")) {
		return res.status(400).json({ success: false, message: "First name must be a non-empty string" });
	}
	if (email !== undefined && email !== null && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
		return res.status(400).json({ success: false, message: "A valid email is required" });
	}
	if ([shiftStart, shiftEnd].some((time) => time !== undefined && time !== null && !TIME_PATTERN.test(time))) {
		return res.status(400).json({ success: false, message: "Shift times must use HH:mm or HH:mm:ss format" });
	}
	if (status !== undefined && !["ACTIVE", "INACTIVE"].includes(status)) {
		return res.status(400).json({ success: false, message: "Status must be ACTIVE or INACTIVE" });
	}
	next();
}

export function validateCreateEmployee(req, res, next) {
	return validateCommonFields(req, res, next);
}

export function validateUpdateEmployee(req, res, next) {
	if (Object.keys(req.body).length === 0) {
		return res.status(400).json({ success: false, message: "At least one field is required to update" });
	}
	return validateCommonFields(req, res, next, { partial: true });
}
