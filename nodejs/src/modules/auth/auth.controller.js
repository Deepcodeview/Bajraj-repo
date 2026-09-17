import { login } from "./auth.service.js";

export async function loginController(req, res) {
  try {
    const { email, password } = req.body;

    if (!email || !password) {
      return res.status(400).json({
        success: false,
        message: "Email and password are required",
      });
    }

    const result = await login(email, password);

    return res.status(200).json({
      success: true,
      message: "Login successful",
      data: result,
    });
  } catch (error) {
    return res.status(401).json({
      success: false,
      message: error.message,
    });
  }
}

export async function meController(req, res) {
  return res.status(200).json({
    success: true,
    message: "Authenticated user",
    data: {
      userId: req.user.userId,
      organizationId: req.user.organizationId,
      role: req.user.role,
    },
  });
}