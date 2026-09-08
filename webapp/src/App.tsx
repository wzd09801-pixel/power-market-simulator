import {
  BookOutlined,
  DashboardOutlined,
  ExperimentOutlined,
  MonitorOutlined,
  SafetyCertificateOutlined,
} from "@ant-design/icons";
import { Layout, Menu, Spin, Tag, Typography } from "antd";
import { lazy, Suspense, useState } from "react";

import { BriefDashboard } from "./components/BriefDashboard";
import "./styles.css";

const { Header, Content, Sider } = Layout;
const ResearchWorkspace = lazy(() =>
  import("./components/ResearchWorkspace").then((module) => ({
    default: module.ResearchWorkspace,
  })),
);
const RecommendationWorkspace = lazy(() =>
  import("./components/RecommendationWorkspace").then((module) => ({
    default: module.RecommendationWorkspace,
  })),
);
const OperationsWorkspace = lazy(() =>
  import("./components/OperationsWorkspace").then((module) => ({
    default: module.OperationsWorkspace,
  })),
);
const navigationItems = [
  {
    key: "brief",
    icon: <DashboardOutlined />,
    label: <span data-testid="nav-brief">今日简报</span>,
  },
  {
    key: "research",
    icon: <BookOutlined />,
    label: <span data-testid="nav-research">证据与研究</span>,
  },
  {
    key: "operations",
    icon: <MonitorOutlined />,
    label: <span data-testid="nav-operations">运行状态</span>,
  },
  {
    key: "recommendation",
    icon: <ExperimentOutlined />,
    label: <span data-testid="nav-recommendation">场景建议</span>,
  },
];

export function App() {
  const [view, setView] = useState("brief");
  const [briefTargetId, setBriefTargetId] = useState<string | null>(null);
  const [recommendationTargetId, setRecommendationTargetId] = useState<string | null>(null);
  const selectView = ({ key }: { key: string }) => setView(key);
  const openActionTarget = (targetType: string, targetId: string) => {
    if (targetType === "intelligence_brief") {
      setBriefTargetId(targetId);
      setView("brief");
    }
    if (targetType === "recommendation") {
      setRecommendationTargetId(targetId);
      setView("recommendation");
    }
  };

  return (
    <Layout className="app-shell">
      <Sider width={248} className="sidebar">
        <div className="brand">
          <SafetyCertificateOutlined />
          <div>
            <strong>示例甲省电力研究台</strong>
            <span>PERSONAL LAB</span>
          </div>
        </div>
        <Menu theme="dark" selectedKeys={[view]} onClick={selectView} items={navigationItems} />
      </Sider>
      <Layout>
        <Header className="topbar">
          <div>
            <Typography.Text strong>Example Province Power Intelligence</Typography.Text>
            <Typography.Text type="secondary">个人研究工作站</Typography.Text>
          </div>
          <Tag color="green">Human-in-the-loop</Tag>
        </Header>
        <Menu
          className="mobile-navigation"
          mode="horizontal"
          selectedKeys={[view]}
          onClick={selectView}
          items={navigationItems}
        />
        <Content className="content">
          {view === "brief" && <BriefDashboard targetBriefId={briefTargetId} />}
          <Suspense fallback={<Spin />}>
            {view === "research" && <ResearchWorkspace />}
            {view === "operations" && <OperationsWorkspace onOpenActionTarget={openActionTarget} />}
            {view === "recommendation" && (
              <RecommendationWorkspace targetRecommendationId={recommendationTargetId} />
            )}
          </Suspense>
        </Content>
      </Layout>
    </Layout>
  );
}
