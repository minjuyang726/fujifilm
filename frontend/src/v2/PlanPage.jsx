import ActionPlan from '../ActionPlan.jsx'
import { FlowBand, PageHead } from './common.jsx'

function PlanPage({ onCheckQuestion }) {
  return (
    <>
      <PageHead page="plan" />
      <FlowBand current="plan" />
      <ActionPlan onCheckQuestion={onCheckQuestion} />
    </>
  )
}

export default PlanPage
