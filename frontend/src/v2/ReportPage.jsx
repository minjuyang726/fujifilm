import Reports from '../Reports.jsx'
import { FlowBand, PageHead } from './common.jsx'

function ReportPage({ onCheckQuestion, selection }) {
  return (
    <>
      <PageHead page="report" />
      <FlowBand current="assemble" />
      <Reports onCheckQuestion={onCheckQuestion} {...selection} />
    </>
  )
}

export default ReportPage
