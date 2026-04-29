import { Key } from "react";
import { Tabs as TabsContainer, TabList, Tab } from "react-aria-components";
import { TabData } from "./types";
import { TabsStyle } from './TabsStyle';

export type TabsProps = {
  tabs: TabData[];
  defaultSelectedTab?: string;
  selectedTab?: string;
  onSelectionChange?: (tabId: string) => void;
  gap?: string;
};

export const Tabs = ({
  tabs,
  defaultSelectedTab,
  selectedTab,
  onSelectionChange,
  gap,
}: TabsProps) => {
  if (!Array.isArray(tabs) || tabs.length === 0) {
    return null;
  }

  return (
    <>
      <TabsStyle />
      <div
        className="c__tabs"
      >
        <TabsContainer
          defaultSelectedKey={defaultSelectedTab}
          selectedKey={selectedTab}
          onSelectionChange={(key: Key) => onSelectionChange?.(String(key))}
        >
          <TabList aria-label="menu" style={{ gap: gap ?? "var(--c--globals--spacings--xxxs)" }}>
            {tabs.map((tab) => (
              <Tab key={tab.id} id={tab.id}>
                {tab.icon && <span aria-hidden="true" className="material-icons">{tab.icon}</span>}
                <span>
                  <span className="react-aria-Tab__title">{tab.label}</span>
                 { tab.subtext && <span className="react-aria-Tab__subtext">{tab.subtext}</span> }
                </span>
              </Tab>
            ))}
          </TabList>
        </TabsContainer>
      </div>
    </>
  );
};
