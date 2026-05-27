import { useQueryClient } from '@tanstack/react-query';
import Image from 'next/image';
import { useEffect } from 'react';
import styled from 'styled-components';

import { KEY_CONFIG } from '@/core/config/api/useConfig';
import type { MaintenanceConfig } from '@/core/config/api/useConfig';

import { MaintenanceIllustration } from './MaintenanceIllustration';

const POLL_INTERVAL_MS = 30_000;

const MARIANNE_PNG =
  'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAIQAAAAwCAMAAADnwSL2AAAAflBMVEUAAJHhAA////8QEJjv7/gwMKYgIJ+/v+RwcMFAQK1QULPf3/GPj8+vr92AgMhgYLr4v8Ofn9bPz+rjEB739/f0n6X73+HwgIfnMDz97/D5z9KoqKiKioqAgIDl5eXKysr2r7Tyj5bsYGnpQEvAwMC4uLjucHjqUFrlIC2YmJgpfk6NAAACI0lEQVRYw73YaWObMAwGYFe+zWGOQJK2uZpe+/9/cJjMW7sVlKwW+pKPPIgXWYR9p2Qu4O+qznc31zcIVsOXdWyXQxiYqmoxhIPpWgrBxQTgHmC9FKKEieqfqIOJG0IvqIOJByIoNu9kCDwQsar+nR6RA1JP9J1QgFVLj6hRxCs9QqCIIz2iAbRackSBI97IESWOWJMj7Dxg/3zYV+QIPiNYPT+8PDzu6BEsm0GsYPWyO3T0CA1zvXjc/Vid6BFmzjA8jAP0Sxxg84o9wDo9wnp72wkGsEmM4HnBb55X92kRsvGMea2L0vDYEZ6lnFdXGETNWF17ZzSEskw6XWoUUSVESCEUU0yaXMc4ZoDX9rRJh5AiD7ceP/t+XV+gji7h2+EaOZ7d4efP4VUrNJh9OkSpw2uhQgK0uTissZxxgSYiGYLnn8Z0Vqprt8ztJhnCxmBArJyPBjyax9QTU/5ufpaPvTCooW+TIuJgEroIqYh9aLBcpkXIRnvOHI+kMvTFeJivtAhV2MvFLz8+tEE4KZAxkRYhP8+NwSBKbgZDo/45xrohCe153VWvpCu/LZ3kTgOE/hjk9okQ0pT68jy++BrsW0qEy8dcqPiHYeF4MCCf4kkRXoBW4/iELHdycs/c3tEhFDSecT5cVZiPNOS0SIuofehCuHU7a4ATZSdiJtXH2YGuc9QrvxojSfs4cMJEdW8LIWwxu0V0G3qEumLHPv8H4idR9Cak2+TKegAAAABJRU5ErkJggg==';

const Root = styled.div`
  min-height: 100vh;
  background-color: #f5f5fe;
  font-family: 'Marianne', arial, sans-serif;
  color: #161616;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 1rem;
  box-sizing: border-box;
`;

const Main = styled.main`
  width: 1200px;
  max-width: 100%;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  flex: 1;
`;

const Container = styled.div`
  width: 100%;
  max-width: 78rem;
  margin: 0 auto;
  padding: 0 1rem;
  display: flex;
  flex-direction: row;
  align-items: center;
  flex: 1;

  @media (min-width: 48em) {
    padding: 0 1.5rem;
  }
`;

const Row = styled.div`
  display: flex;
  flex-direction: row;
  flex-wrap: wrap;
  width: 100%;
  justify-content: center;
  align-items: center;
`;

const Body = styled.div`
  flex: 0 0 100%;
  width: 100%;
  max-width: 100%;
  margin-top: 3.5rem;
  margin-bottom: 3.5rem;

  @media (min-width: 48em) {
    flex: 0 0 50%;
    width: 50%;
    max-width: 50%;
  }
`;

const Illustration = styled.div`
  display: flex;
  flex-direction: row;
  align-items: center;
  justify-content: center;
  margin-bottom: 3.5rem;
  flex: 0 0 100%;
  width: 100%;
  max-width: 100%;

  @media (max-width: 47.99999em) {
    display: none;
  }

  @media (min-width: 48em) {
    flex: 0 0 25%;
    width: 25%;
    max-width: 25%;
    margin-top: 3.5rem;
    margin-left: 8.3333333333%;
  }

  svg {
    max-width: 300px;
    height: auto;
    width: 100%;
  }
`;

const Title = styled.h1`
  font-size: 2rem;
  line-height: 2.5rem;
  margin: 0 0 1.5rem;
  font-weight: 700;

  @media (min-width: 48em) {
    font-size: 2.5rem;
    line-height: 3rem;
  }
`;

const Paragraph = styled.p`
  font-size: 1.25rem;
  line-height: 2rem;
  margin: 0 0 1.5rem;
`;

const Bold = styled.span`
  font-weight: 700;
`;

const Actions = styled.p`
  display: flex;
  align-items: baseline;
  gap: 1rem;
  margin: 0 0 1.5rem;

  @media (max-width: 47.99999em) {
    display: block;
    flex-direction: column;
  }
`;

const ActionLink = styled.a`
  color: #000091;
  text-underline-offset: 3px;
  display: flex;
  align-items: center;
  gap: 6px;
  text-decoration: underline;

  &:hover {
    text-decoration: underline;
    text-decoration-thickness: 2px;
  }
`;

const Footer = styled.div`
  display: flex;
  justify-content: center;
  margin-top: 3.5rem;
  margin-bottom: 2rem;
  width: 100%;
`;

type Props = {
  maintenance: MaintenanceConfig;
};

export const MaintenancePage = ({ maintenance }: Props) => {
  const queryClient = useQueryClient();

  useEffect(() => {
    const id = window.setInterval(() => {
      void queryClient.invalidateQueries({ queryKey: [KEY_CONFIG] });
    }, POLL_INTERVAL_MS);
    return () => window.clearInterval(id);
  }, [queryClient]);

  const moreInfo = maintenance.message?.trim();

  return (
    <Root>
      <Main role="main" id="content">
        <Container>
          <Row>
            <Body>
              <Title>Service indisponible</Title>
              <Paragraph>
                <Bold>Le service </Bold>
                est en cours de maintenance, veuillez nous excuser pour la gêne
                occasionnée.
              </Paragraph>
              {moreInfo && <Paragraph>{moreInfo}</Paragraph>}
              <Actions>
                <ActionLink
                  aria-label="Découvrir La Suite (nouvelle fenêtre)"
                  target="_blank"
                  rel="noreferrer"
                  href="https://lasuite.numerique.gouv.fr/"
                >
                  <span>Découvrir La Suite</span>
                  <svg
                    width="16"
                    height="16"
                    xmlns="http://www.w3.org/2000/svg"
                    viewBox="0 0 24 24"
                    fill="currentColor"
                    aria-hidden="true"
                  >
                    <path d="M10 6V8H5V19H16V14H18V20C18 20.5523 17.5523 21 17 21H4C3.44772 21 3 20.5523 3 20V7C3 6.44772 3.44772 6 4 6H10ZM21 3V11H19L18.9999 6.413L11.2071 14.2071L9.79289 12.7929L17.5849 5H13V3H21Z" />
                  </svg>
                </ActionLink>
              </Actions>
            </Body>
            <Illustration>
              <MaintenanceIllustration />
            </Illustration>
          </Row>
        </Container>
        <Footer>
          <Image
            width={66}
            height={24}
            src={MARIANNE_PNG}
            alt="Marianne"
            unoptimized
          />
        </Footer>
      </Main>
    </Root>
  );
};
