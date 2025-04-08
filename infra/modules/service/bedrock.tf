#-----------------
# Bedrock Access for using LiteLLM
#-----------------
resource "aws_iam_policy" "bedrock" {
  name        = "${var.service_name}-bedrock-access"
  description = "Allow access to AWS Bedrock from LiteLLM"
  policy      = data.aws_iam_policy_document.bedrock.json
}

data "aws_iam_policy_document" "bedrock" {
  # https://github.com/BerriAI/litellm/discussions/8949
  statement {
    sid    = "BedrockAccess"
    effect = "Allow"
    actions = [
      "bedrock:InvokeModel",
      "bedrock:InvokeModelWithResponseStream"
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy_attachment" "bedrock" {
  role       = aws_iam_role.app_service.name
  policy_arn = aws_iam_policy.bedrock.arn
}
