import Reports from '../Reports.jsx'
import { FlowBand, PageHead } from './common.jsx'

function ReportPage({ onCheckQuestion }) {
  return (
    <>
      <PageHead page="report" />
      <FlowBand current="assemble" />
      <Reports onCheckQuestion={onCheckQuestion} />
    </>
  )
}

export default ReportPage
