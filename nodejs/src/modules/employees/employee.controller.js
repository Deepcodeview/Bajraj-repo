import { createEmployee, getEmployees, getEmployeeById, updateEmployee, deleteEmployee } from "./employee.service.js";

function resolveStoreId(req, requestedStoreId) {
  if (req.user.role === "ADMIN" && req.user.storeId) {
    if (requestedStoreId && requestedStoreId !== req.user.storeId) {
      throw new Error("You are not permitted to act on a different store");
    }
    return req.user.storeId;
  }
  return requestedStoreId;
}

export async function createEmployeeController(req, res) {
	try {
		const storeId = resolveStoreId(req, req.body.storeId);
		const employee = await createEmployee(req.user.organizationId, { ...req.body, storeId });
		return res.status(201).json({ success: true, message: "Employee created successfully", data: employee });
	} catch (error) {
		return res.status(400).json({ success: false, message: error.message });
	}
}

export async function getEmployeesController(req, res) {
	try {
		const storeId = resolveStoreId(req, req.query.storeId);
		const employees = await getEmployees(req.user.organizationId, storeId);
		return res.status(200).json({ success: true, data: employees });
	} catch (error) {
		return res.status(500).json({ success: false, message: error.message });
	}
}

export async function getEmployeeByIdController(req, res) {
	try {
		const employee = await getEmployeeById(req.user.organizationId, req.params.id);
		if (req.user.role === "ADMIN" && req.user.storeId && employee.store_id !== req.user.storeId) {
			return res.status(403).json({ success: false, message: "Access denied" });
		}
		return res.status(200).json({ success: true, data: employee });
	} catch (error) {
		return res.status(404).json({ success: false, message: error.message });
	}
}

export async function updateEmployeeController(req, res) {
	try {
		const existing = await getEmployeeById(req.user.organizationId, req.params.id);
		if (req.user.role === "ADMIN" && req.user.storeId && existing.store_id !== req.user.storeId) {
			return res.status(403).json({ success: false, message: "Access denied" });
		}
		const employee = await updateEmployee(req.user.organizationId, req.params.id, req.body);
		return res.status(200).json({ success: true, message: "Employee updated successfully", data: employee });
	} catch (error) {
		return res.status(400).json({ success: false, message: error.message });
	}
}

export async function deleteEmployeeController(req, res) {
	try {
		const existing = await getEmployeeById(req.user.organizationId, req.params.id);
		if (req.user.role === "ADMIN" && req.user.storeId && existing.store_id !== req.user.storeId) {
			return res.status(403).json({ success: false, message: "Access denied" });
		}
		await deleteEmployee(req.user.organizationId, req.params.id);
		return res.status(200).json({ success: true, message: "Employee deleted successfully" });
	} catch (error) {
		return res.status(404).json({ success: false, message: error.message });
	}
}
