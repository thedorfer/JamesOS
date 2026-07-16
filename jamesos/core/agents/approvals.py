from .models import RiskLevel
class ApprovalPolicy:
    denied={RiskLevel.DESTRUCTIVE,RiskLevel.FINANCIAL,RiskLevel.ORDER}
    explicit={RiskLevel.REMOTE_WRITE,RiskLevel.PUBLICATION}
    def evaluate(self,request,reference=None):
        if request.risk_level in self.denied:return False
        if request.risk_level in self.explicit or request.approval_requirement.required:return bool(reference and (not request.approval_requirement.scope or request.approval_requirement.scope in reference))
        return True

