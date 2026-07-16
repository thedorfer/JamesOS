from .models import RiskLevel
class ApprovalPolicy:
    denied={RiskLevel.DESTRUCTIVE,RiskLevel.FINANCIAL,RiskLevel.ORDER}
    explicit={RiskLevel.REMOTE_WRITE,RiskLevel.PUBLICATION}
    def evaluate(self,request,reference=None):
        if request.risk_level in self.denied:return False
        if request.risk_level in self.explicit or request.approval_requirement.required:
            if not reference or (request.approval_requirement.scope and request.approval_requirement.scope not in reference):return False
            return not request.approval_requirement.reference or reference==f"approved:{request.approval_requirement.scope}:{request.approval_requirement.reference}"
        return True
