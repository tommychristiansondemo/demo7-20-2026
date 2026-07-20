import { Amplify } from "aws-amplify";

const amplifyConfig = {
  Auth: {
    Cognito: {
      userPoolId: import.meta.env.VITE_COGNITO_USER_POOL_ID || "",
      userPoolClientId: import.meta.env.VITE_COGNITO_CLIENT_ID || "",
    },
  },
};

export function configureAmplify() {
  Amplify.configure(amplifyConfig);
}
