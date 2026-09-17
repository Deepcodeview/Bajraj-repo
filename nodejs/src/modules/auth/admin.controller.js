import { createAdmin } from "./admin.service.js";

export async function createAdminController(req, res) {
  try {
    const organizationId = req.body.organizationId || req.user.organizationId;
    const admin = await createAdmin(organizationId, req.body);
    return res.status(201).json({ success: true, message: "Admin created successfully", data: admin });
  } catch (error) {
    return res.status(400).json({ success: false, message: error.message });
  }
}