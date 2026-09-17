import prisma from "../../config/database.js";

function generateRuleCode() {
  const random = Math.random().toString(36).substring(2, 8).toUpperCase();
  return `RULE-${Date.now()}-${random}`;
}

export async function createRule(organizationId, data) {
  if (data.storeId) {
    const store = await prisma.stores.findFirst({
      where: { id: data.storeId, organization_id: organizationId },
    });
    if (!store) {
      throw new Error("Store not found for this organization");
    }
  }

  if (data.zoneId) {
    const zone = await prisma.zones.findFirst({
      where: { id: data.zoneId, organization_id: organizationId },
    });
    if (!zone) {
      throw new Error("Zone not found for this organization");
    }
  }

  const rule = await prisma.business_rules.create({
    data: {
      organization_id: organizationId,
      store_id: data.storeId || null,
      zone_id: data.zoneId || null,
      rule_code: generateRuleCode(),
      name: data.name,
      rule_type: data.ruleType,
      event_type: data.eventType || null,
      condition_config: data.conditionConfig || null,
      threshold_config: data.thresholdConfig || null,
      severity: data.severity || "MEDIUM",
      is_active: true,
    },
  });

  return rule;
}

export async function getRules(organizationId, filters = {}) {
  const { storeId, ruleType, isActive } = filters;

  const where = { organization_id: organizationId };

  if (storeId) where.store_id = storeId;
  if (ruleType) where.rule_type = ruleType;
  if (isActive !== undefined) where.is_active = isActive === "true" || isActive === true;

  return prisma.business_rules.findMany({
    where,
    orderBy: { created_at: "desc" },
  });
}

export async function getRuleById(organizationId, ruleId) {
  const rule = await prisma.business_rules.findFirst({
    where: { id: ruleId, organization_id: organizationId },
  });

  if (!rule) {
    throw new Error("Business rule not found");
  }

  return rule;
}

export async function updateRule(organizationId, ruleId, data) {
  await getRuleById(organizationId, ruleId); // throws if not found/not yours

  const updateData = {};
  if (data.name !== undefined) updateData.name = data.name;
  if (data.conditionConfig !== undefined) updateData.condition_config = data.conditionConfig;
  if (data.thresholdConfig !== undefined) updateData.threshold_config = data.thresholdConfig;
  if (data.severity !== undefined) updateData.severity = data.severity;
  if (data.isActive !== undefined) updateData.is_active = data.isActive;

  const updated = await prisma.business_rules.update({
    where: { id: ruleId },
    data: updateData,
  });

  return updated;
}
