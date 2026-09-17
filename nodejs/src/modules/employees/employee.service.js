import prisma from "../../config/database.js";

function toTimeDate(value) {
	if (value === undefined || value === null) return value;
	return new Date(`1970-01-01T${value.length === 5 ? `${value}:00` : value}.000Z`);
}

function employeeData(data) {
	const result = {};
	const fields = ["storeId", "employeeCode", "erpEmployeeId", "firstName", "lastName", "phone", "email", "status"];
	for (const field of fields) {
		if (data[field] !== undefined) {
			const databaseField = field.replace(/[A-Z]/g, (letter) => `_${letter.toLowerCase()}`);
			result[databaseField] = data[field] === "" ? null : data[field];
		}
	}
	if (data.shiftStart !== undefined) result.shift_start = toTimeDate(data.shiftStart);
	if (data.shiftEnd !== undefined) result.shift_end = toTimeDate(data.shiftEnd);
	return result;
}

async function assertStoreBelongsToOrganization(organizationId, storeId) {
	const store = await prisma.stores.findFirst({ where: { id: storeId, organization_id: organizationId } });
	if (!store) throw new Error("Store not found in this organization");
}

async function generateEmployeeCode(organizationId) {
	const last = await prisma.employees.findFirst({
		where: { organization_id: organizationId, employee_code: { startsWith: "EMP" } },
		orderBy: { employee_code: "desc" },
		select: { employee_code: true },
	});
	const next = last ? parseInt(last.employee_code.replace("EMP", ""), 10) + 1 : 1;
	return `EMP${String(next).padStart(4, "0")}`;
}

export async function createEmployee(organizationId, data) {
	await assertStoreBelongsToOrganization(organizationId, data.storeId);
	const employee_code = data.employeeCode?.trim() || await generateEmployeeCode(organizationId);
	return prisma.employees.create({ data: { organization_id: organizationId, ...employeeData(data), employee_code } });
}

export async function getEmployees(organizationId, storeId) {
	const where = { organization_id: organizationId };
	if (storeId) where.store_id = storeId;
	return prisma.employees.findMany({ where, orderBy: { created_at: "desc" } });
}

export async function getEmployeeById(organizationId, employeeId) {
	const employee = await prisma.employees.findFirst({ where: { id: employeeId, organization_id: organizationId } });
	if (!employee) throw new Error("Employee not found");
	return employee;
}

export async function updateEmployee(organizationId, employeeId, data) {
	const employee = await getEmployeeById(organizationId, employeeId);
	if (data.storeId && data.storeId !== employee.store_id) await assertStoreBelongsToOrganization(organizationId, data.storeId);
	return prisma.employees.update({
		where: { id: employee.id },
		data: { ...employeeData(data), updated_at: new Date() },
	});
}

export async function deleteEmployee(organizationId, employeeId) {
	const employee = await getEmployeeById(organizationId, employeeId);
	await prisma.employees.delete({ where: { id: employee.id } });
}
