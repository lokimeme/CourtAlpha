"""
CourtAlpha Visual Intelligence Engine
Generates professional-grade, interactive NBA shot charts.
Uses Plotly for court geometry and coordinate mapping.
"""

import plotly.graph_objects as go
import pandas as pd

class ShotChartEngine:
    def __init__(self):
        # NBA Court Dimensions (in tenths of a foot)
        self.court_width = 500
        self.half_court_length = 470
        self.hoop_center_y = 0
        self.hoop_center_x = 0
        
    def draw_court_shapes(self, fig):
        """Adds standard NBA court markings to a Plotly figure."""
        
        # 1. The Hoop (Rim)
        fig.add_shape(type="circle", x0=-7.5, y0=-7.5, x1=7.5, y1=7.5, line_color="white")
        
        # 2. The Backboard
        fig.add_shape(type="line", x0=-30, y0=-7.5, x1=30, y1=-7.5, line_color="white")
        
        # 3. The Paint (Outer Box)
        fig.add_shape(type="rect", x0=-80, y0=-47.5, x1=80, y1=142.5, line_color="white")
        
        # 4. The Free Throw Circle
        fig.add_shape(type="circle", x0=-60, y0=142.5-60, x1=60, y1=142.5+60, line_color="white")
        
        # 5. The Restricted Area
        fig.add_shape(type="circle", x0=-40, y0=-0, x1=40, y1=40, line_color="white")
        
        # 6. The Three Point Arc (Sides)
        fig.add_shape(type="line", x0=-220, y0=-47.5, x1=-220, y1=92.5, line_color="white")
        fig.add_shape(type="line", x0=220, y0=-47.5, x1=220, y1=92.5, line_color="white")
        
        # 7. The Three Point Arc (Top)
        # Simplified as an arc for Plotly
        fig.add_trace(go.Scatter(
            x=[-220, 0, 220],
            y=[92.5, 237.5, 92.5],
            mode='lines',
            line=dict(color='white', width=1, shape='spline'),
            showlegend=False,
            hoverinfo='skip'
        ))
        
        return fig

    def create_shot_chart(self, player_shots, player_name=""):
        """Generates an interactive scatter-based shot chart."""
        
        fig = go.Figure()
        
        if player_shots.empty:
            fig.update_layout(title="No Shot Data Available")
            return fig

        # Separate Makes and Misses
        makes = player_shots[player_shots['SHOT_MADE_FLAG'] == 1]
        misses = player_shots[player_shots['SHOT_MADE_FLAG'] == 0]

        # Add Misses (Red) - Added first so they are in the background
        fig.add_trace(go.Scatter(
            x=misses['LOC_X'],
            y=misses['LOC_Y'],
            mode='markers',
            name='Missed',
            marker=dict(size=6, color='#FF4B4B', opacity=0.5, symbol='x')
        ))

        # Add Makes (Green)
        fig.add_trace(go.Scatter(
            x=makes['LOC_X'],
            y=makes['LOC_Y'],
            mode='markers',
            name='Made',
            marker=dict(size=7, color='#00CC96', opacity=0.8, symbol='circle')
        ))

        # Add Court Lines
        fig = self.draw_court_shapes(fig)

        # Layout and Styling
        fig.update_layout(
            title=f"Shot Profile: {player_name}",
            template="plotly_dark",
            showlegend=True,
            xaxis=dict(showgrid=False, zeroline=False, visible=False, range=[-250, 250]),
            yaxis=dict(showgrid=False, zeroline=False, visible=False, range=[-50, 420], scaleanchor="x"),
            width=600,
            height=500,
            margin=dict(l=20, r=20, t=60, b=20),
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)'
        )

        return fig

if __name__ == "__main__":
    # Test with mock data
    engine = ShotChartEngine()
    mock_data = pd.DataFrame({
        'LOC_X': [0, 100, -200, 50, -50],
        'LOC_Y': [10, 50, 250, 300, 150],
        'SHOT_MADE_FLAG': [1, 0, 1, 0, 1]
    })
    fig = engine.create_shot_chart(mock_data, "Test Player")
    print("Shot Chart Engine Ready.")
