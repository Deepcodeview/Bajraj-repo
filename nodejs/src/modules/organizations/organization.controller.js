import {
  createOrganization,
  getOrganizations,
  getOrganizationById,
  updateOrganization,
} from "./organization.service.js";

export async function createOrganizationController(req, res) {
  try {
    const organization = await createOrganization(req.body);
    return res.status(201).json({
      success: true,
      message: "Organization created successfully",
      data: organization,
    });
  } catch (error) {
    return res.status(400).json({ success: false, message: error.message });
  }
}

export async function getOrganizationsController(req, res) {
  try {
    const organizations = await getOrganizations();
    return res.status(200).json({ success: true, data: organizations });
  } catch (error) {
    return res.status(500).json({ success: false, message: error.message });
  }
}

export async function getOrganizationByIdController(req, res) {
  try {
    const organization = await getOrganizationById(req.params.id);
    return res.status(200).json({ success: true, data: organization });
  } catch (error) {
    return res.status(404).json({ success: false, message: error.message });
  }
}

export async function updateOrganizationController(req, res) {
  try {
    const organization = await updateOrganization(req.params.id, req.body);
    return res.status(200).json({
      success: true,
      message: "Organization updated successfully",
      data: organization,
    });
  } catch (error) {
    return res.status(400).json({ success: false, message: error.message });
  }
}
