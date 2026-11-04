import ActionPlan from '../ActionPlan.jsx'
import { FlowBand, PageHead } from './common.jsx'

function PlanPage({ onCheckQuestion, selection }) {
  return (
    <>
      <PageHead page="plan" />
      <FlowBand current="plan" />
      <ActionPlan onCheckQuestion={onCheckQuestion} {...selection} />
    </>
  )
}

export default PlanPage
