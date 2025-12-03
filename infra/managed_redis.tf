resource "azapi_resource" "azure_managed_redis" {
  type = "Microsoft.Cache/redisEnterprise@2025-05-01-preview"
  name = format("amr-%s", local.resource_suffix_kebabcase)
  parent_id = local.resource_group_id
  location = local.resource_group_location
  body = {
    properties = {
      highAvailability  = "Enabled"
      minimumTlsVersion = "1.2"
    }
    sku = {
      name = "Balanced_B0"
    }
  }
  ignore_casing             = false
  ignore_missing_property   = true
  ignore_null_property      = false
  schema_validation_enabled = true
  tags = local.tags_azapi
  identity {
    identity_ids = []
    type         = "SystemAssigned"
  }
}
